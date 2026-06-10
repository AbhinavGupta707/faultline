"""voice_gateway — Gemini Live API bridge.

Voice-IN  (WS /voice/intent): push-to-talk mic audio → transcript + parsed intent.
Voice-OUT (WS /voice/call):   in-app two-party negotiation call with streaming transcript
                              + audio (faultline_agent vs supplier persona, both Gemini).

Two modes (config.py): ``live`` = real Vertex Live API; ``mock`` = fixture-driven, no creds.
A standalone test page is served at ``GET /`` so this service is developable + demoable with
zero dependency on the rest of the UI. Contracts: http_api.md (voice_gateway) + the
voice_in_*/voice_call_* / call_event_payload / voice_intent schemas (FROZEN).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import mock
from config import CONFIG, describe
from intent import rule_based_intent
from personas import DEMO_CONTEXT

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("voice_gateway")

app = FastAPI(title="voice-gateway")

_HERE = os.path.dirname(os.path.abspath(__file__))
_STATIC = os.path.join(_HERE, "static")
if os.path.isdir(_STATIC):
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# server→client audio is chunked into frames of this size (bytes)
_AUDIO_FRAME = 8192
_SENTINEL = object()


# ── basic routes ──────────────────────────────────────────────────────────────
@app.get("/")
def index():
    page = os.path.join(_STATIC, "index.html")
    if os.path.exists(page):
        return FileResponse(page)
    return JSONResponse({"service": "voice-gateway", "hint": "static test page not found"})


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "voice-gateway",
        "version": "0.2.0",
        "mode": CONFIG.mode,
        **describe(),
    }


# ── helpers ────────────────────────────────────────────────────────────────────
async def _send_json(ws: WebSocket, obj: dict):
    await ws.send_text(json.dumps(obj))


async def _send_audio(ws: WebSocket, pcm: bytes, rate: int):
    """audio.start (JSON) followed by chunked binary PCM16 frames — the contract framing."""
    await _send_json(ws, {"type": "audio.start", "sample_rate_hz": rate})
    for i in range(0, len(pcm), _AUDIO_FRAME):
        await ws.send_bytes(pcm[i:i + _AUDIO_FRAME])


# ── WS /voice/intent — push-to-talk voice in ───────────────────────────────────
@app.websocket("/voice/intent")
async def voice_intent(ws: WebSocket):
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue()
    pending_approval_id: str | None = None
    mock_text: str | None = None
    proc_task: asyncio.Task | None = None
    started = False

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break

            if msg.get("bytes") is not None:
                if started:
                    await queue.put(msg["bytes"])
                continue

            text = msg.get("text")
            if text is None:
                continue
            try:
                ctrl = json.loads(text)
            except json.JSONDecodeError:
                continue

            mtype = ctrl.get("type")
            if mtype == "start":
                started = True
                pending_approval_id = ctrl.get("pending_approval_id") or pending_approval_id
                # optional mock-mode transcript hint (ignored in live mode); extra field is allowed
                mock_text = ctrl.get("text") or ctrl.get("mock_transcript")
                if CONFIG.is_live:
                    proc_task = asyncio.create_task(
                        _run_live_intent(ws, queue, pending_approval_id)
                    )
            elif mtype == "stop":
                if not started:
                    continue
                started = False
                if CONFIG.is_live and proc_task is not None:
                    await queue.put(_SENTINEL)
                    await proc_task
                    proc_task = None
                else:
                    await _emit_mock_intent(ws, mock_text, pending_approval_id)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 — surface, never crash the socket
        log.exception("voice/intent error")
        try:
            await _send_json(ws, {"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if proc_task and not proc_task.done():
            proc_task.cancel()


async def _emit_mock_intent(ws: WebSocket, mock_text: str | None, pending_approval_id: str | None):
    transcript, intent = mock.mock_intent(mock_text, pending_approval_id)
    # exercise the partial path with a couple of word-chunks
    words = transcript.split()
    acc: list[str] = []
    for i, w in enumerate(words):
        acc.append(w)
        if i % 3 == 2 and i < len(words) - 1:
            await _send_json(ws, {"type": "transcript.partial", "text": " ".join(acc)})
            await asyncio.sleep(0.05)
    await _send_json(ws, {"type": "transcript.final", "text": transcript})
    await _send_json(ws, {"type": "intent", "transcript": transcript, "intent": intent})


async def _run_live_intent(ws: WebSocket, queue: asyncio.Queue, pending_approval_id: str | None):
    import live  # lazy — only imported in live mode

    async def chunks():
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                return
            yield item

    async def on_partial(text: str):
        await _send_json(ws, {"type": "transcript.partial", "text": text})

    try:
        transcript, intent = await live.transcribe_and_parse(chunks(), pending_approval_id, on_partial)
    except Exception as exc:  # noqa: BLE001 — degrade to rule-based, keep the demo alive
        log.exception("live intent failed; falling back to rule-based")
        await _send_json(ws, {"type": "error", "message": f"live intent fell back: {exc}"})
        transcript, intent = "", rule_based_intent("", pending_approval_id)

    await _send_json(ws, {"type": "transcript.final", "text": transcript})
    await _send_json(ws, {"type": "intent", "transcript": transcript, "intent": intent})


# ── WS /voice/call — in-app negotiation call (voice out) ────────────────────────
@app.websocket("/voice/call")
async def voice_call(ws: WebSocket):
    await ws.accept()
    play_task: asyncio.Task | None = None
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            text = msg.get("text")
            if text is None:
                continue
            try:
                ctrl = json.loads(text)
            except json.JSONDecodeError:
                continue

            mtype = ctrl.get("type")
            if mtype == "call.start":
                call_id = ctrl.get("call_id") or "call-local"
                po_id = ctrl.get("po_id") or DEMO_CONTEXT.po_id
                if play_task and not play_task.done():
                    play_task.cancel()
                play_task = asyncio.create_task(_run_call(ws, call_id, po_id))
            elif mtype == "call.end":
                if play_task and not play_task.done():
                    play_task.cancel()
                await _send_json(ws, {
                    "type": "call.event",
                    "payload": {"call_id": ctrl.get("call_id") or "call-local",
                                "event": "status", "status": "ended"},
                })
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.exception("voice/call error")
        try:
            await _send_json(ws, {"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if play_task and not play_task.done():
            play_task.cancel()


async def _emit_call_event(ws: WebSocket, payload: dict):
    await _send_json(ws, {"type": "call.event", "payload": payload})


async def _run_call(ws: WebSocket, call_id: str, po_id: str):
    try:
        if CONFIG.is_live:
            await _run_call_live(ws, call_id, po_id)
        else:
            await _run_call_mock(ws, call_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — fall back to the scripted call so the demo survives
        log.exception("live call failed; falling back to mock")
        await _send_json(ws, {"type": "error", "message": f"call fell back to scripted: {exc}"})
        await _run_call_mock(ws, call_id)


async def _run_call_mock(ws: WebSocket, call_id: str):
    async for item in mock.stream_mock_call(call_id):
        if "audio_start" in item:
            await _send_json(ws, {"type": "audio.start", "sample_rate_hz": item["audio_start"]})
        elif "audio" in item:
            pcm = item["audio"]
            for i in range(0, len(pcm), _AUDIO_FRAME):
                await ws.send_bytes(pcm[i:i + _AUDIO_FRAME])
        elif "json" in item:
            await _emit_call_event(ws, item["json"])


async def _run_call_live(ws: WebSocket, call_id: str, po_id: str):
    import live  # lazy

    ctx = DEMO_CONTEXT  # in prod, hydrate from the approved PO (po_id) via the agent runtime
    await _emit_call_event(ws, {"call_id": call_id, "event": "status", "status": "initiating"})
    await _emit_call_event(ws, {"call_id": call_id, "event": "status", "status": "connected"})

    last_summary_emitted = False
    async for speaker, text, audio in live.run_negotiation_call(ctx):
        if audio:
            await _send_audio(ws, audio, CONFIG.output_sample_rate_hz)
        await _emit_call_event(ws, {
            "call_id": call_id, "event": "transcript",
            "speaker": speaker, "text": text, "is_final": True,
        })

    # Best-effort agreement summary mirroring the approved PO.
    await _emit_call_event(ws, {
        "call_id": call_id, "event": "summary",
        "summary": {
            "agreed": True, "lead_time_days": 7, "expedited_lead_time_days": 7,
            "quantity": ctx.quantity, "unit_price_usd": ctx.unit_price_usd,
            "notes": f"Agent self-identified as AI; commitment contingent on PO approval ({ctx.po_id}).",
        },
    })
    await _emit_call_event(ws, {"call_id": call_id, "event": "status", "status": "ended"})
    _ = last_summary_emitted

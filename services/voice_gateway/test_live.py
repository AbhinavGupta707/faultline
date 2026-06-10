"""Live end-to-end test through the real gateway WS (needs VOICE_MODE=live + ADC).

Skipped automatically unless VOICE_MODE=live. Exercises:
  * /voice/call  — a real two-party negotiation call (native audio + transcript)
  * /voice/intent — Gemini speaks a command, we stream it in, assert the parsed intent
All Google AI. Run in the WSL venv:
  VOICE_MODE=live GCP_PROJECT=faultline-hack VERTEX_LOCATION=us-central1 \
  VOICE_CALL_MAX_TURNS=2 GOOGLE_CLOUD_PROJECT=faultline-hack \
  pytest test_live.py -q -s
"""
from __future__ import annotations

import asyncio
import json
import os
import struct

import pytest
from fastapi.testclient import TestClient

if os.getenv("VOICE_MODE") != "live":
    pytest.skip("live tests require VOICE_MODE=live + ADC", allow_module_level=True)

import main  # noqa: E402
import live  # noqa: E402


def _resample(pcm: bytes, src: int, dst: int) -> bytes:
    n = len(pcm) // 2
    xs = struct.unpack(f"<{n}h", pcm)
    r = src / dst
    out = bytearray()
    for i in range(int(n / r)):
        p = i * r
        a = int(p)
        b = min(a + 1, n - 1)
        out += struct.pack("<h", int(xs[a] + (xs[b] - xs[a]) * (p - a)))
    return bytes(out)


async def _synthesize_16k(text: str) -> bytes:
    """Speak `text` verbatim via the native-audio model → PCM16 @16k for the mic input."""
    from google.genai import types

    client = live._client()
    model = await live.resolve_model(client)
    cfg = {
        "response_modalities": ["AUDIO"],
        "system_instruction": "You are a TTS engine. Speak the user's message verbatim.",
        "output_audio_transcription": {},
    }
    audio = bytearray()
    async with client.aio.live.connect(model=model, config=cfg) as s:
        await s.send_client_content(turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True)
        async for m in s.receive():
            if getattr(m, "data", None):
                audio.extend(m.data)
            sc = getattr(m, "server_content", None)
            if sc and getattr(sc, "turn_complete", False):
                break
    return _resample(bytes(audio), 24000, 16000)


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


def test_live_call(client):
    with client.websocket_connect("/voice/call") as ws:
        ws.send_json({"type": "call.start", "call_id": "call-live-01", "po_id": "po-2026-0042"})
        statuses, speakers, summary, audio_frames = [], set(), None, 0
        for _ in range(4000):
            data = ws.receive()
            if data.get("bytes") is not None:
                audio_frames += 1
                continue
            msg = json.loads(data["text"])
            if msg["type"] != "call.event":
                continue
            p = msg["payload"]
            if p["event"] == "status":
                statuses.append(p["status"])
                if p["status"] in ("ended", "failed"):
                    break
            elif p["event"] == "transcript":
                speakers.add(p["speaker"])
                print(f"  {p['speaker']}: {p['text'][:80]}")
            elif p["event"] == "summary":
                summary = p["summary"]
    assert statuses and statuses[-1] == "ended"
    assert speakers == {"faultline_agent", "supplier"}, speakers
    assert audio_frames > 0, "expected real native-audio frames"
    assert summary is not None


def test_live_intent(client):
    pcm16 = asyncio.run(_synthesize_16k("approve the re-source for the cold-brew line"))
    assert len(pcm16) > 0
    with client.websocket_connect("/voice/intent") as ws:
        ws.send_json({"type": "start", "sample_rate_hz": 16000, "encoding": "pcm16",
                      "pending_approval_id": "apr-resource-coldbrew-01"})
        for i in range(0, len(pcm16), 3200):
            ws.send_bytes(pcm16[i:i + 3200])
        ws.send_json({"type": "stop"})
        intent = None
        transcript = ""
        for _ in range(200):
            msg = ws.receive_json()
            if msg["type"] == "transcript.final":
                transcript = msg["text"]
            elif msg["type"] == "intent":
                intent = msg["intent"]
                break
        print(f"\n  transcript: {transcript!r}\n  intent: {intent}")
    assert intent is not None
    assert transcript.strip(), "expected a non-empty transcript from native-audio STT"
    assert intent["action"] in ("approve", "query", "show"), intent

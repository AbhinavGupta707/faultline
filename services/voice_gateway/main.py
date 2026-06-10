"""voice_gateway — Gemini Live API bridge: voice-in (push-to-talk → intent) and
voice-out (in-app negotiation call with streaming transcript).

Phase 0 stub — Session E implements per impl plan §7 + contracts/http_api.md
(WS /voice/intent, WS /voice/call; audio framing PCM16 16k in / 24k out).
Primary model gemini-3.1-flash-live-preview; fallback gemini-live-2.5-flash-native-audio.
"""
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="voice-gateway")


@app.get("/health")
def health():
    return {"ok": True, "service": "voice-gateway",
            "version": "phase0-stub",
            "mode": os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")}


@app.websocket("/voice/intent")
async def voice_intent(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive()
            if msg.get("text") and json.loads(msg["text"]).get("type") == "stop":
                await ws.send_text(json.dumps({"type": "error", "message": "phase0 stub — Live API not wired yet"}))
    except WebSocketDisconnect:
        pass


@app.websocket("/voice/call")
async def voice_call(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.receive_text()
            await ws.send_text(json.dumps({"type": "error", "message": "phase0 stub — Live API not wired yet"}))
    except WebSocketDisconnect:
        pass

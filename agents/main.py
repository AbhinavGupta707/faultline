"""Faultline agent runtime — FastAPI app: ADK Runner + WebSocket bridge.

Phase 0 stub (Session B implements per impl plan §6). The HTTP/WS surface below is
contract-shaped (contracts/http_api.md, contracts/ws_protocol.md) so the frontend and
deploy pipeline can integrate before the agents exist.
"""
import json
import os
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="faultline-agent")

ELASTIC_MODE = os.getenv("ELASTIC_MODE", "mock")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@app.get("/health")
def health():
    return {"ok": True, "service": "faultline-agent", "mode": ELASTIC_MODE, "elastic_ok": ELASTIC_MODE == "mock"}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    """Streams every plan step / tool call / emission per contracts/ws_protocol.md.

    Stub: sends one contract-valid `status` message, then echoes client messages' types.
    Session B replaces this with the Runner-callback narration bridge.
    """
    await websocket.accept()
    await websocket.send_text(json.dumps({
        "type": "status", "ts": _now(), "run_id": None,
        "payload": {"mode": "live", "feeds_ok": False, "elastic_ok": False,
                    "active_run_id": None, "note": "phase0 stub — no agents wired yet"},
    }))
    try:
        while True:
            await websocket.receive_text()  # accept and ignore client messages for now
    except WebSocketDisconnect:
        pass


@app.post("/whatif")
async def whatif(body: dict):
    scenario = body.get("scenario", {})
    return {
        "accepted": True,
        "run_id": "run-stub-0000",
        "event_id": f"evt-whatif-stub-{scenario.get('preset', 'custom')}",
    }


@app.post("/approval")
async def approval(body: dict):
    return {"ok": True, "approval_id": body.get("approval_id", ""), "applied": False}

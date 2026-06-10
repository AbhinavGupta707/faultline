"""End-to-end mock-mode tests for the voice gateway WS contracts.

Runs with no GCP creds (VOICE_MODE defaults to mock). Drives /voice/intent and /voice/call
through Starlette's TestClient and validates every server message against the FROZEN schemas.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

os.environ.setdefault("VOICE_MODE", "mock")

import main  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(6):
    cand = os.path.join(ROOT, "contracts", "schemas", "faultline.schema.json")
    if os.path.exists(cand):
        break
    ROOT = os.path.dirname(ROOT)
with open(cand, encoding="utf-8") as fh:
    SCHEMA = json.load(fh)


def validator(defname: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/$defs/{defname}", "$defs": SCHEMA["$defs"]})


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["service"] == "voice-gateway"
    validator("health_response").validate(body)


@pytest.mark.parametrize("text,expected", [
    ("what's my biggest risk right now?", "query"),
    ("show the coffee chain", "show"),
    ("approve the re-source for the cold-brew line", "approve"),
    ("reject that", "reject"),
    ("what if Busan port closes ten days", "whatif"),
])
def test_voice_intent(client, text, expected):
    vi_server = validator("voice_in_server_msg")
    vi = validator("voice_intent")
    with client.websocket_connect("/voice/intent") as ws:
        ws.send_json({"type": "start", "sample_rate_hz": 16000, "encoding": "pcm16",
                      "pending_approval_id": "apr-1", "text": text})
        ws.send_json({"type": "stop"})
        got_intent = None
        for _ in range(40):
            msg = ws.receive_json()
            vi_server.validate(msg)
            if msg["type"] == "intent":
                got_intent = msg
                break
        assert got_intent is not None
        vi.validate(got_intent["intent"])
        assert got_intent["intent"]["action"] == expected
        assert got_intent["transcript"] == text
        if expected in ("approve", "reject"):
            assert got_intent["intent"]["approval_id"] == "apr-1"


def test_voice_call(client):
    ce = validator("call_event_payload")
    vc_server = validator("voice_call_server_msg")
    with client.websocket_connect("/voice/call") as ws:
        ws.send_json({"type": "call.start", "call_id": "call-test-01", "po_id": "po-2026-0042"})
        statuses, speakers, summary, audio_frames = [], set(), None, 0
        for _ in range(400):
            data = ws.receive()
            if "bytes" in data and data["bytes"] is not None:
                audio_frames += 1
                continue
            msg = json.loads(data["text"])
            vc_server.validate(msg)
            if msg["type"] != "call.event":
                continue
            p = msg["payload"]
            ce.validate(p)
            assert p["call_id"] == "call-test-01"
            if p["event"] == "status":
                statuses.append(p["status"])
            elif p["event"] == "transcript":
                speakers.add(p["speaker"])
            elif p["event"] == "summary":
                summary = p["summary"]
            if statuses and statuses[-1] == "ended":
                break
        assert statuses[0] == "initiating" and statuses[-1] == "ended"
        assert "connected" in statuses
        assert speakers == {"faultline_agent", "supplier"}
        assert summary is not None and summary["agreed"] is True
        assert audio_frames > 0  # 24 kHz placeholder audio streamed

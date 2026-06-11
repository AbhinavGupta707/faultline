"""App-surface tests: /health, /ws boot, POST /whatif → full simulated run over
the live socket, POST /approval round-trip + idempotency (contracts/http_api.md)."""
import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from agents.main import app

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/schemas/faultline.schema.json").read_text(encoding="utf-8"))
WHATIF_REQUEST = json.loads(
    (ROOT / "contracts/fixtures/whatif_scenario.json").read_text(encoding="utf-8"))


def validate_ws(msg: dict) -> None:
    jsonschema.validate(msg, {"$ref": "#/$defs/ws_message", "$defs": SCHEMA["$defs"]})


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    import os
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["service"] == "faultline-agent"
    assert body["mode"] == os.environ["ELASTIC_MODE"]
    jsonschema.validate(body, {"$ref": "#/$defs/health_response", "$defs": SCHEMA["$defs"]})


def test_ws_boot_status(client):
    with client.websocket_connect("/ws") as ws:
        msg = json.loads(ws.receive_text())
        validate_ws(msg)
        assert msg["type"] == "status"
        assert msg["run_id"] is None
        assert msg["seq"] == 0


def test_events_recent(client):
    from agents.main import STATE
    STATE.events_cache = None  # isolate from other tests' cache
    resp = client.get("/events/recent")
    assert resp.status_code == 200
    events = resp.json()
    assert 0 < len(events) <= 25
    for e in events:
        assert set(e) == {"id", "title", "source", "published_at", "place_name",
                          "lat", "lon", "severity", "url", "relevant"}
        assert isinstance(e["lat"], (int, float)) and isinstance(e["lon"], (int, float))
    published = [e["published_at"] for e in events]
    assert published == sorted(published, reverse=True), "not newest-first"
    assert not any(e["id"].startswith("evt-whatif") for e in events), "simulated leaked"

    # limit respected (and served from the 30s cache as a prefix slice)
    short = client.get("/events/recent?limit=2").json()
    assert len(short) == 2
    assert short == events[:2]
    assert STATE.events_cache is not None

    # relevant:true on ids the last run's Watcher flagged (flags are computed
    # per-request, so they update even when the event list is cached)
    flagged = events[0]["id"]
    STATE.last_relevant_ids = {flagged}
    try:
        again = client.get("/events/recent").json()
        assert [e["id"] for e in again if e["relevant"]] == [flagged]
    finally:
        STATE.last_relevant_ids = set()


def test_unknown_approval_not_applied(client):
    resp = client.post("/approval", json={"approval_id": "appr-nope", "approved": True})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "approval_id": "appr-nope", "applied": False}


def test_whatif_full_run_over_ws(client):
    """POST /whatif → synthetic simulated:true event → identical pipeline →
    approval gate round-trip → verified narration, all on the live socket."""
    with client.websocket_connect("/ws") as ws:
        boot = json.loads(ws.receive_text())
        assert boot["type"] == "status"

        resp = client.post("/whatif", json=WHATIF_REQUEST)
        assert resp.status_code == 202
        body = resp.json()
        assert body["accepted"] is True
        assert body["event_id"].startswith("evt-whatif-minas-frost")
        run_id = body["run_id"]

        messages = []
        approval_id = None
        # drain to the approval gate
        for _ in range(200):
            msg = json.loads(ws.receive_text())
            validate_ws(msg)
            messages.append(msg)
            if msg["type"] == "approval.request":
                approval_id = msg["payload"]["approval_id"]
                break
        assert approval_id, "never reached the approval gate"
        assert all(m["run_id"] == run_id for m in messages)

        relevant = next(m for m in messages
                        if m["type"] == "agent.emit"
                        and m["payload"]["kind"] == "relevant_events")
        events = relevant["payload"]["payload"]["events"]
        assert len(events) == 1
        assert events[0]["simulated"] is True
        assert events[0]["source"] == "whatif"

        ranked = next(m for m in messages
                      if m["type"] == "agent.emit"
                      and m["payload"]["kind"] == "ranked_exposures")
        exposures = ranked["payload"]["payload"]["exposures"]
        assert exposures, "no exposures from the frost scenario"
        assert all(e["simulated"] is True for e in exposures)
        assert exposures[0]["product_id"] == "prd-coldbrew-12oz"

        # approve via HTTP (same semantics as ws approval.decision)
        resp = client.post("/approval",
                           json={"approval_id": approval_id, "approved": True, "note": "go"})
        assert resp.json() == {"ok": True, "approval_id": approval_id, "applied": True}

        # idempotent: a second decision is not applied
        resp = client.post("/approval", json={"approval_id": approval_id, "approved": False})
        assert resp.json()["applied"] is False

        # drain to the end of the run
        saw_verify = saw_final_status = False
        for _ in range(300):
            msg = json.loads(ws.receive_text())
            validate_ws(msg)
            if msg["type"] == "agent.emit" and msg["payload"]["kind"] == "verify_result":
                saw_verify = True
            if msg["type"] == "decision.logged":
                assert msg["payload"]["simulated"] is True
            if msg["type"] == "status" and msg["run_id"] == run_id:
                saw_final_status = True
                break
        assert saw_verify and saw_final_status

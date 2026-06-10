"""THE golden-path test (impl plan §15, parallel plan §3 definition of done).

Fixture event in (mock mode, zero cloud deps) → contract-valid ranked_exposures
+ decision-log writes + complete WS narration out, type-sequence-compatible with
contracts/fixtures/ws_replay.jsonl.

Replay-comparison filter: tool.call lines are excluded (chip cadence may differ),
`dir:"c2s"` lines are operator choreography, boot `status` (run_id null) is
app-level, and `brief` emissions/decisions belong to Session G's depth agents
(the registry ships empty — the core narration must be identical either way).
"""
import asyncio
import json
from pathlib import Path

import jsonschema
import pytest

from agents import orchestrator
from agents.approvals import ApprovalRegistry
from agents.bus import Bus
from agents.context import RunContext
from agents.llm import Gemini
from agents.mocks import elastic_fake
from agents.tools.elastic_mcp import ToolBelt
from agents.tools.po import generate_po_pdf

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/schemas/faultline.schema.json").read_text(encoding="utf-8"))
REPLAY = [
    json.loads(line)
    for line in (ROOT / "contracts/fixtures/ws_replay.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]

GOLDEN_EVENT = "evt-gdacs-flood-guj-20260610"


def validate_ws(msg: dict) -> None:
    jsonschema.validate(msg, {"$ref": "#/$defs/ws_message", "$defs": SCHEMA["$defs"]})


def validate_decision(doc: dict) -> None:
    jsonschema.validate(doc, {"$ref": "#/$defs/decision", "$defs": SCHEMA["$defs"]})


def phase_signature(msgs: list[dict]) -> list[tuple]:
    sig = []
    for m in msgs:
        if m.get("dir") == "c2s":
            continue
        t = m["type"]
        if t == "tool.call":
            continue
        if t == "status" and m.get("run_id") is None:
            continue
        if t == "agent.emit":
            kind = m["payload"]["kind"]
            if kind == "brief":
                continue
            sig.append(("agent.emit", kind))
        elif t == "decision.logged":
            if m["payload"]["kind"] == "brief":
                continue
            sig.append(("decision.logged", m["payload"]["kind"]))
        else:
            sig.append((t,))
    return sig


async def _run_golden(approve: bool = True, note: str | None = None):
    bus = Bus()
    approvals = ApprovalRegistry()
    tools = ToolBelt(bus)
    tools.register_local("generate_po_pdf", generate_po_pdf)
    ctx = RunContext(run_id="run-2026-06-10-0001", mode="live", bus=bus,
                     tools=tools, llm=Gemini(), approvals=approvals)

    async def auto_decider():
        while not approvals.pending_ids():
            await asyncio.sleep(0.005)
        approvals.resolve(approvals.pending_ids()[0], approve, note)

    decider = asyncio.create_task(auto_decider())
    try:
        await asyncio.wait_for(orchestrator.run_pipeline(ctx), timeout=30)
    finally:
        decider.cancel()
    return list(bus.history), ctx


@pytest.fixture()
def golden_run():
    return asyncio.run(_run_golden(approve=True, note="Proceed with the recommended alternate."))


def test_every_message_is_contract_valid(golden_run):
    messages, _ = golden_run
    assert len(messages) > 30
    for msg in messages:
        validate_ws(msg)


def test_ws_narration_type_sequence_matches_replay(golden_run):
    messages, _ = golden_run
    assert phase_signature(messages) == phase_signature(REPLAY)


def test_all_replay_message_types_are_narrated(golden_run):
    messages, _ = golden_run
    mine = {m["type"] for m in messages}
    expected = {m["type"] for m in REPLAY
                if m.get("dir") != "c2s" and not (
                    m["type"] == "agent.emit" and m["payload"]["kind"] == "brief")}
    assert expected <= mine


def test_ranked_exposures_values(golden_run):
    messages, _ = golden_run
    ranked = [m for m in messages
              if m["type"] == "agent.emit" and m["payload"]["kind"] == "ranked_exposures"]
    assert len(ranked) == 1
    exposures = ranked[0]["payload"]["payload"]["exposures"]
    assert len(exposures) == 2

    granola, sparkling = exposures
    assert granola["rank"] == 1
    assert granola["product_id"] == "prd-granola-bar"
    assert granola["component_id"] == "cmp-emulsifier"
    assert granola["status"] == "at_risk"
    assert granola["days_of_cover"] == 9
    assert granola["est_disruption_days"] == 21
    assert granola["dollars_at_risk_usd"] == 460000
    assert granola["severity"] == 0.84
    assert granola["chokepoint_supplier_id"] == "sup-vadodara-chem"
    assert granola["root_cause_event_id"] == GOLDEN_EVENT
    assert GOLDEN_EVENT in granola["evidence_event_ids"]

    assert sparkling["rank"] == 2
    assert sparkling["product_id"] == "prd-sparkling-botanical"
    assert sparkling["status"] == "watch"
    assert sparkling["dollars_at_risk_usd"] == 95000
    assert sparkling["severity"] == 0.58


def test_decision_log_writes(golden_run):
    _, _ctx = golden_run
    decisions = elastic_fake.decisions()
    kinds = [d["kind"] for d in decisions]
    assert kinds == ["triage", "trace", "assess", "approval", "resource", "negotiate", "verify"]
    for doc in decisions:
        validate_decision(doc)
        assert doc["evidence_event_ids"], f"decision {doc['decision_id']} lacks evidence"
        assert doc["run_id"] == "run-2026-06-10-0001"


def test_tool_calls_paired_and_elastic_flagged(golden_run):
    messages, _ = golden_run
    calls = [m["payload"] for m in messages if m["type"] == "tool.call"]
    assert calls, "no tool.call narration"
    by_id: dict[str, list[str]] = {}
    for c in calls:
        by_id.setdefault(c["call_id"], []).append(c["status"])
        expected_elastic = c["tool"] != "generate_po_pdf"
        assert c["elastic"] is expected_elastic, c["tool"]
    for call_id, statuses in by_id.items():
        assert statuses in (["start", "ok"], ["ok"]), (call_id, statuses)
    tools_used = {c["tool"] for c in calls}
    assert {"search_events", "match_event_to_suppliers", "traverse_supply_graph",
            "lookup_exposure", "find_alternate_suppliers", "write_decision",
            "generate_po_pdf"} <= tools_used


def test_resource_and_verify_payloads(golden_run):
    messages, _ = golden_run
    emits = {m["payload"]["kind"]: m["payload"]["payload"] for m in messages
             if m["type"] == "agent.emit"}

    alts = emits["alternates"]
    assert alts["recommended_supplier_id"] == "sup-jurong-chem"
    assert alts["component_id"] == "cmp-emulsifier"
    assert len(alts["alternates"]) == 3

    po = emits["draft_po"]
    assert po["supplier_id"] == "sup-jurong-chem"
    assert po["contingent"] is True
    assert po["status"] == "draft"
    assert po["total_usd"] == round(po["quantity"] * po["unit_price_usd"], 2)
    assert po["pdf_gcs_uri"].startswith("gs://")
    assert po["lead_time_days"] == 7

    vr = emits["verify_result"]
    assert vr["gap_closed"] is True
    assert vr["margin_days"] == 2
    assert vr["status_change"] == {"from": "at_risk", "to": "secured"}
    assert vr["residual_risk"]["level"] == "medium"


def test_depth_state_keys_present(golden_run):
    """The exact shared session-state keys depth agents read (components.md §3)."""
    _, ctx = golden_run
    for key in ("run_meta", "relevant_events", "exposure_paths", "ranked_exposures",
                "alternates", "draft_po", "verify_result"):
        assert key in ctx.state, f"missing depth-contract state key: {key}"
    assert ctx.state["run_meta"]["run_id"] == ctx.run_id
    assert ctx.state["run_meta"]["mode"] == "live"


def test_rejection_path_skips_action_stages():
    messages, _ = asyncio.run(_run_golden(approve=False, note="hold for now"))
    for msg in messages:
        validate_ws(msg)
    kinds = [m["payload"]["kind"] for m in messages if m["type"] == "agent.emit"]
    assert "alternates" not in kinds and "draft_po" not in kinds
    assert "verify_result" not in kinds

    final_plan = [m for m in messages if m["type"] == "plan.update"][-1]
    statuses = {s["id"]: s["status"] for s in final_plan["payload"]["steps"]}
    assert statuses["resource"] == "skipped"
    assert statuses["verify"] == "skipped"
    assert statuses["approve"] == "done"

    decisions = elastic_fake.decisions()
    approval = next(d for d in decisions if d["kind"] == "approval")
    assert "rejected" in approval["summary"]
    assert messages[-1]["type"] == "status"

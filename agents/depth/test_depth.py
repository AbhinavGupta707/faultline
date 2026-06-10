"""Depth-lane tests — schema-validate every emitted shape against the FROZEN contract.

Runs fully offline (FAULTLINE_WAREHOUSE=local). No cloud, no LLM. This is the lane's
golden-path guard: brief payload, analytics summary, and warehouse rows all validate
against contracts/schemas/faultline.schema.json before integration.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

os.environ.setdefault("FAULTLINE_WAREHOUSE", "local")

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts" / "schemas" / "faultline.schema.json").read_text("utf-8"))


def _validator(defname: str) -> Draft202012Validator:
    schema = {"allOf": [{"$ref": f"#/$defs/{defname}"}], "$defs": SCHEMA["$defs"]}
    return Draft202012Validator(schema)


def _check(defname: str, instance) -> None:
    errs = sorted(_validator(defname).iter_errors(instance), key=lambda e: e.path)
    assert not errs, f"{defname}: " + "; ".join(f"{list(e.path)}: {e.message}" for e in errs[:5])


def test_brief_payload_valid():
    from agents.depth.briefer import produce_brief
    from agents.depth.runstate import RunState

    res = produce_brief(RunState.golden())
    _check("brief_payload", res.payload)
    assert res.payload["headline_metric"]["value"] == "$460,000"
    assert res.payload["evidence_event_ids"], "brief must cite evidence"
    _check("decision", res.decision)
    assert res.decision["kind"] == "brief"


def test_brief_pdf_is_valid():
    from agents.depth.briefer import produce_brief
    from agents.depth.runstate import RunState

    res = produce_brief(RunState.golden())
    pdf = (ROOT / "agents" / "depth" / "_artifacts" / "reports" / f"{res.payload['report_id']}.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-"), "not a PDF"
    assert b"%%EOF" in pdf[-1024:], "missing EOF"
    assert len(pdf) > 800


def test_backfill_and_analytics():
    from agents.depth.bq_export import backfill
    from agents.depth.analytics import summarize
    from agents.depth.warehouse import LocalWarehouse
    import tempfile

    wh = LocalWarehouse(Path(tempfile.mkdtemp()) / "wh")
    totals = backfill(days=60, end=date(2026, 6, 10), reset=True, warehouse=wh)
    assert totals["runs"] >= 30, totals
    summary = summarize(60, today=date(2026, 6, 10), warehouse=wh)
    _check("analytics_summary", summary)
    assert summary["runs_count"] >= 30
    assert summary["dollars_at_risk_avoided_usd"] > 0
    # the sole-source emulsifier plant should be the top recurring chokepoint
    assert summary["top_chokepoints"][0]["supplier_id"] == "sup-vadodara-chem"


def test_analytics_fixture_fallback_when_empty():
    from agents.depth.analytics import summarize
    from agents.depth.warehouse import LocalWarehouse
    import tempfile

    wh = LocalWarehouse(Path(tempfile.mkdtemp()) / "empty")
    summary = summarize(60, today=date(2026, 6, 10), warehouse=wh)
    _check("analytics_summary", summary)  # falls back to golden fixture, still valid


def test_export_golden_run_rows_valid():
    from agents.depth.bq_export import run_rows
    from agents.depth.runstate import RunState

    rows = run_rows(RunState.golden(), backfill=False)
    assert len(rows["runs"]) == 1
    assert len(rows["exposures"]) == 3
    assert rows["runs"][0]["dollars_at_risk_avoided_usd"] == 460000


def test_enricher_reemits_valid_ranked_exposures():
    from agents.depth.enrich import run_enricher
    from agents.depth.runstate import RunState

    res = run_enricher(RunState.golden())
    _check("ranked_exposures_payload", res.payload)
    assert res.payload["enriched"] is True
    _check("decision", res.decision)
    assert res.decision["kind"] == "enrich"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

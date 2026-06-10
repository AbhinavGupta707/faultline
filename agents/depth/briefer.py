"""Briefer — cited executive situation report from full run state (Session G).

Consumes the shared session-state (RunState) and produces a markdown + PDF brief written
to GCS, plus a contract-valid `$defs/brief_payload` emitted as `agent.emit kind:"brief"`
so the Decision Log header can link the report. Every claim carries evidence_event_ids.

The report is composed *deterministically* from the structured run state — not free-form
LLM prose — so it is always correctly cited and reproducible (the polished demo case
first; impl plan §1.10). An optional Gemini-3.5-flash polish pass can smooth wording when
`BRIEFER_LLM=1` and google-genai is available, but it never invents claims or citations.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .artifacts import ArtifactStore
from .pdfgen import markdown_to_pdf
from .runstate import RunState

AGENT = "briefer"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _money(v: float | int | None) -> str:
    return f"${float(v or 0):,.0f}"


def _unit_price(v: float | int | None) -> str:
    return f"${float(v or 0):,.2f}"


def _report_id(run_id: str) -> str:
    # run-2026-06-10-0001 → rpt-20260610-0001
    parts = run_id.replace("run-", "").split("-")
    if len(parts) >= 4:
        return f"rpt-{parts[0]}{parts[1]}{parts[2]}-{parts[3]}"
    return f"rpt-{run_id}"


def _region(place_name: str) -> str:
    bits = [b.strip() for b in (place_name or "").split(",") if b.strip()]
    return bits[1] if len(bits) >= 2 else (bits[0] if bits else "the region")


def _component_label(component_id: str | None) -> str:
    return (component_id or "component").replace("cmp-", "").replace("-", " ")


@dataclass
class BriefResult:
    payload: dict[str, Any]      # $defs/brief_payload
    markdown: str
    decision: dict[str, Any]     # $defs/decision (kind="brief")


# ── composition ─────────────────────────────────────────────────────────────────
def _title(state: RunState) -> str:
    root = state.root_event
    top = state.exposures[0] if state.exposures else {}
    status_word = "secured" if state.secured else (
        "at risk" if any(e.get("status") == "at_risk" for e in state.exposures) else "monitored"
    )
    comp = _component_label(top.get("component_id"))
    return f"Situation Report — {_region(root.get('place_name', ''))} {root.get('event_type', 'disruption')}: {comp} supply {status_word}"


def _highlights(state: RunState) -> list[str]:
    out: list[str] = []
    root = state.root_event
    exposures = sorted(state.exposures, key=lambda e: e.get("rank", 99))
    top = exposures[0] if exposures else None

    if root and top:
        out.append(
            f"{root.get('title') or root.get('event_type', 'A disruption').capitalize()} "
            f"({root.get('place_name', 'the region')}) threatens the "
            f"{_component_label(top.get('component_id'))} supply; estimated "
            f"{int(top.get('est_disruption_days', 0))}-day disruption."
        )
    if top:
        watch = next((e for e in exposures[1:] if e.get("status") in ("watch", "at_risk")), None)
        line = (
            f"Critical exposure: {top.get('product_name')} — {int(top.get('days_of_cover', 0))} days of cover, "
            f"{_money(top.get('dollars_at_risk_usd'))} at risk"
        )
        if watch:
            line += f"; {watch.get('product_name')} on watch ({int(watch.get('days_of_cover', 0))} days of cover)"
        out.append(line + ".")

    po = state.draft_po
    if po:
        air = " (split air/sea)" if po.get("ship_mode") == "split" else ""
        out.append(
            f"Re-sourced to {po.get('supplier_name')} under contingent PO {po.get('po_id')}: "
            f"{po.get('quantity'):,.0f} {po.get('unit')} at {_unit_price(po.get('unit_price_usd'))}/{po.get('unit')}{air}, "
            f"need-by {po.get('need_by_date')}."
        )

    vr = state.verify_result
    if vr:
        risk = (vr.get("residual_risk") or {}).get("level", "unknown")
        if vr.get("gap_closed"):
            out.append(
                f"Supplier confirmed; Verifier confirms the gap is closed with "
                f"{int(vr.get('margin_days', 0))} days of margin. Residual risk: {risk}."
            )
        else:
            out.append(f"Gap NOT yet closed — residual risk: {risk}. Escalation recommended.")
    return out


def _markdown(state: RunState, report_id: str, generated_at: str) -> str:
    root = state.root_event
    exposures = sorted(state.exposures, key=lambda e: e.get("rank", 99))
    top = exposures[0] if exposures else {}
    po = state.draft_po
    vr = state.verify_result
    status_word = "SECURED" if state.secured else (
        "AT RISK" if any(e.get("status") == "at_risk" for e in exposures) else "MONITORED"
    )
    avoided = state.dollars_at_risk_avoided

    L: list[str] = []
    L.append(f"# {_title(state)}")
    L.append(
        f"**Run** `{state.run_id}` · **Generated** {generated_at[:16].replace('T', ' ')} UTC · "
        f"**Status:** {status_word} · **$ at risk averted: {_money(avoided)}**"
    )
    if state.simulated:
        L.append("\n> ⚠ SIMULATED — what-if scenario run, not a live incident.")

    # What happened
    L.append("\n## What happened")
    if root:
        L.append(
            f"{root.get('why_relevant') or root.get('title', 'A disruption was detected.')} "
            f"Estimated disruption: **{int(top.get('est_disruption_days', 0))} days**. "
            f"[evidence: `{root.get('event_id')}`]"
        )

    # Exposure table
    L.append("\n## Exposure")
    L.append("| Product | Days of cover | $ at risk | Status |")
    L.append("|---|---|---|---|")
    for e in exposures:
        arrow = " → **secured**" if e.get("status") == "secured" else ""
        status = ("at risk" if e.get("status") == "at_risk" else e.get("status", "")) + arrow
        L.append(
            f"| {e.get('product_name')} | {int(e.get('days_of_cover', 0))} | "
            f"{_money(e.get('dollars_at_risk_usd'))} | {status} |"
        )
    if top:
        L.append(
            f"\n{top.get('rationale', '')}".rstrip()
        )

    # Action taken
    if po:
        L.append("\n## Action taken")
        rec = state.alternates.get("recommended_supplier_id")
        alt_count = len(state.alternates.get("alternates") or [])
        chosen = next(
            (a for a in (state.alternates.get("alternates") or []) if a.get("supplier_id") == rec),
            None,
        )
        score = f" (match score {chosen.get('match_score')})" if chosen else ""
        L.append(
            f"- **Re-sourced** to **{po.get('supplier_name')}**{score}, selected from "
            f"{alt_count} qualified alternate(s)."
        )
        L.append(
            f"- **Contingent PO `{po.get('po_id')}`**: {po.get('quantity'):,.0f} {po.get('unit')} "
            f"@ {_unit_price(po.get('unit_price_usd'))}/{po.get('unit')} = **{_money(po.get('total_usd'))}**, "
            f"ship mode {po.get('ship_mode')}, need-by {po.get('need_by_date')}."
        )
        if po.get("notes"):
            L.append(f"- {po.get('notes')}")

    # Verification
    if vr:
        L.append("\n## Verification")
        rr = vr.get("residual_risk") or {}
        L.append(vr.get("summary", ""))
        if rr.get("factors"):
            L.append(f"**Residual risk: {rr.get('level', 'unknown')}** — " + "; ".join(rr["factors"]) + ".")

    # Watching (lower-severity exposures / secondary events)
    watch_events = [e for e in state.relevant_events if e.get("event_id") != root.get("event_id")]
    if watch_events:
        L.append("\n## Watching")
        for w in watch_events:
            L.append(f"- {w.get('why_relevant', w.get('title'))} [evidence: `{w.get('event_id')}`]")

    # Evidence footer (every report lists its sources)
    L.append("\n---")
    L.append("**Evidence** — " + ", ".join(f"`{eid}`" for eid in state.all_evidence_event_ids))
    return "\n".join(L)


def _maybe_polish(markdown: str) -> str:
    """Optional Gemini-3.5-flash wording pass; off by default, never changes facts."""
    if os.getenv("BRIEFER_LLM") != "1":
        return markdown
    try:
        from google import genai  # lazy

        client = genai.Client()
        model = os.getenv("GEMINI_MODEL_FLASH", "gemini-3.5-flash")
        prompt = (
            "Lightly copy-edit this executive supply-chain situation report for clarity and tone. "
            "Do NOT add, remove, or alter any number, id, date, or `[evidence: ...]` citation. "
            "Return markdown only.\n\n" + markdown
        )
        resp = client.models.generate_content(model=model, contents=prompt)
        text = (resp.text or "").strip()
        return text if text else markdown
    except Exception:
        return markdown


# ── public entry points ───────────────────────────────────────────────────────────
def produce_brief(state: RunState, store: ArtifactStore | None = None) -> BriefResult:
    store = store or ArtifactStore()
    report_id = _report_id(state.run_id)
    generated_at = _now_iso()
    markdown = _maybe_polish(_markdown(state, report_id, generated_at))
    pdf_bytes = markdown_to_pdf(markdown, title=_title(state))

    md_art = store.write(f"reports/{report_id}.md", markdown.encode("utf-8"), "text/markdown")
    pdf_art = store.write(f"reports/{report_id}.pdf", pdf_bytes, "application/pdf")
    # also mirror under run_id so /report/{run_id} resolves without an index
    store.write(f"reports/by-run/{state.run_id}.md", markdown.encode("utf-8"), "text/markdown")
    store.write(f"reports/by-run/{state.run_id}.pdf", pdf_bytes, "application/pdf")

    top = state.exposures[0] if state.exposures else {}
    payload = {
        "report_id": report_id,
        "run_id": state.run_id,
        "title": _title(state),
        "generated_at": generated_at,
        "headline_metric": {
            "label": "$ at risk averted" if state.secured else "$ at risk",
            "value": _money(state.dollars_at_risk_avoided if state.secured else state.dollars_at_risk_total),
        },
        "highlights": _highlights(state),
        "markdown_gcs_uri": md_art.uri,
        "pdf_gcs_uri": pdf_art.uri,
        "download_path": f"/report/{state.run_id}",
        "evidence_event_ids": state.all_evidence_event_ids,
    }
    decision = {
        "decision_id": f"dec-{report_id}",
        "run_id": state.run_id,
        "ts": generated_at,
        "agent": AGENT,
        "kind": "brief",
        "summary": (
            f"Situation report {report_id} generated: "
            f"{sum(1 for e in state.exposures if e.get('status') == 'secured')} exposure(s) secured "
            f"({_money(state.dollars_at_risk_avoided)} at risk averted), "
            f"{sum(1 for e in state.exposures if e.get('status') == 'watch')} watch item(s)."
        ),
        "evidence_event_ids": state.all_evidence_event_ids,
        "simulated": state.simulated,
        "related": {"report_id": report_id, "product_ids": [e.get("product_id") for e in state.exposures]},
    }
    return BriefResult(payload=payload, markdown=markdown, decision=decision)


def run_briefer(state: RunState, emit: Callable[[str, dict], None] | None = None,
               store: ArtifactStore | None = None) -> BriefResult:
    """Produce the brief and (optionally) emit it through the host's WS callback.

    `emit(kind, payload)` is the orchestrator's narration hook; when absent (standalone
    dev / tests) we just return the result. Never raises into the core loop.
    """
    result = produce_brief(state, store=store)
    if emit:
        emit("brief", result.payload)
    return result


if __name__ == "__main__":
    import json

    res = produce_brief(RunState.golden())
    print(json.dumps(res.payload, indent=2))
    print("\n--- markdown ---\n")
    print(res.markdown)

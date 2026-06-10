"""Enricher — multimodal severity refinement from a recall PDF (Session G).

Given a recall notice PDF (and optionally a disaster image) referenced by an event, the
Enricher extracts structured facts (affected lots, recall date, classification, scope)
and refines the affected exposures' severity, then re-emits `ranked_exposures` with
`enriched: true` (contracts/components.md §3) and writes a `kind:"enrich"` decision.

Per the brief: one POLISHED scripted example first, generalize after. The scripted demo
is a Class II elderflower-extract recall hitting the Vela Sparkling line — a *confirmed*
contamination, which the model promotes above a merely-forecast weather risk. Fact
extraction is deterministic (regex over the recall text) so the demo never flakes; an
optional Gemini-3.5-flash multimodal pass (ENRICH_LLM=1 + google-genai) can read an
arbitrary PDF/image, but the structured refinement below is the load-bearing path.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .pdfgen import markdown_to_pdf
from .runstate import RunState

AGENT = "enricher"

# ── the polished scripted demo: a Class II elderflower-extract recall ──────────────
RECALL_NOTICE_MD = """# FDA Food Enforcement Report — Voluntary Recall

**Recall Number:** F-1287-2026
**Status:** Ongoing
**Classification:** Class II
**Recalling Firm:** Grasse Botanique SARL (Grasse, France)
**Product:** Elderflower Botanical Extract, food-grade, 25 kg drums
**Reason for Recall:** Possible Salmonella contamination identified during routine finished-product testing.
**Recall Initiated:** 2026-06-08
**Distribution:** Netherlands, United States (CA, OR), Singapore
**Affected Lots:** GB-ELD-2026-0419, GB-ELD-2026-0422, GB-ELD-2026-0431
**Quantity:** 4,800 kg
"""

RECALL_EVENT = {
    "event_id": "evt-openfda-recall-elderflower-20260608",
    "title": "Class II recall — elderflower botanical extract (possible Salmonella), Grasse Botanique SARL",
    "source": "openfda",
    "event_type": "recall",
    "severity_raw": 0.55,
    "location": {"lat": 43.6589, "lon": 6.926},
    "place_name": "Grasse, France",
    "published_at": "2026-06-08T14:00:00Z",
    "url": "gs://faultline-assets/recalls/F-1287-2026.pdf",
    "simulated": False,
    "why_relevant": "Grasse Botanique supplies the elderflower extract for the Vela Sparkling Botanicals line; a Class II recall is a confirmed contamination, not a forecast risk.",
    "supplier_hints": ["sup-grasse-botanicals"],
}

# pre-enrichment exposure (botanical extract chain) the Enricher will refine
_PRE_ENRICH_EXPOSURE = {
    "exposure_id": "exp-sparkling-botanical-recall",
    "rank": 1,
    "product_id": "prd-sparkling-botanical",
    "product_name": "Vela Sparkling Botanicals",
    "component_id": "cmp-botanical-extract",
    "root_cause_event_id": RECALL_EVENT["event_id"],
    "chokepoint_supplier_id": "sup-grasse-botanicals",
    "days_of_cover": 22,
    "est_disruption_days": 10,
    "dollars_at_risk_usd": 0,
    "monthly_revenue_usd": 950000,
    "severity": 0.35,
    "status": "watch",
    "rationale": "Botanical extract supplier flagged in an openFDA recall feed; scope and affected lots unconfirmed pending document review.",
    "evidence_event_ids": [RECALL_EVENT["event_id"]],
    "path_ids": [],
    "simulated": False,
}


def recall_pdf_bytes() -> bytes:
    """Render the scripted recall notice to a PDF (stands in for the openFDA document)."""
    return markdown_to_pdf(RECALL_NOTICE_MD, title="FDA Food Enforcement Report F-1287-2026")


def enrich_demo_state() -> RunState:
    """The polished standalone demo run-state (recall event + pre-enrichment exposure)."""
    return RunState(
        {
            "run_meta": {"run_id": "run-2026-06-08-recall", "mode": "live",
                         "started_at": "2026-06-08T14:05:00Z"},
            "relevant_events": {"events": [RECALL_EVENT]},
            "ranked_exposures": {"exposures": [_PRE_ENRICH_EXPOSURE]},
        }
    )


# ── fact extraction (deterministic; optional LLM multimodal override) ───────────────
@dataclass
class RecallFacts:
    lots: list[str] = field(default_factory=list)
    recall_initiated: str | None = None
    classification: str | None = None
    distribution: list[str] = field(default_factory=list)
    reason: str | None = None
    quantity: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "lots": self.lots,
            "recall_initiated": self.recall_initiated,
            "classification": self.classification,
            "distribution": self.distribution,
            "reason": self.reason,
            "quantity": self.quantity,
        }


def _split_top(s: str) -> list[str]:
    """Split on commas/semicolons at parenthesis depth 0 (keeps 'US (CA, OR)' intact)."""
    out, buf, depth = [], [], 0
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in ",;" and depth == 0:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf).strip())
    return [t for t in out if t]


def extract_recall_facts(text: str) -> RecallFacts:
    f = RecallFacts()
    m = re.search(r"Affected Lots:\*{0,2}\s*(.+)", text)
    if m:
        f.lots = _split_top(m.group(1))
    m = re.search(r"Recall Initiated:\*{0,2}\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        f.recall_initiated = m.group(1)
    m = re.search(r"Classification:\*{0,2}\s*(Class\s+[IVX]+)", text)
    if m:
        f.classification = m.group(1)
    m = re.search(r"Distribution:\*{0,2}\s*(.+)", text)
    if m:
        f.distribution = _split_top(m.group(1))
    m = re.search(r"Reason for Recall:\*{0,2}\s*(.+)", text)
    if m:
        f.reason = m.group(1).strip()
    m = re.search(r"Quantity:\*{0,2}\s*(.+)", text)
    if m:
        f.quantity = m.group(1).strip()
    return f


def _llm_extract(pdf_bytes: bytes, image_path: str | None) -> RecallFacts | None:
    """Optional Gemini-3.5-flash multimodal extraction. Off unless ENRICH_LLM=1."""
    if os.getenv("ENRICH_LLM") != "1":
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client()
        model = os.getenv("GEMINI_MODEL_FLASH", "gemini-3.5-flash")
        parts: list[Any] = [
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            "Extract recall facts as JSON with keys lots[], recall_initiated, classification, "
            "distribution[], reason, quantity. Return JSON only.",
        ]
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as fh:
                parts.insert(1, types.Part.from_bytes(data=fh.read(), mime_type="image/jpeg"))
        resp = client.models.generate_content(model=model, contents=parts)
        import json as _json

        raw = re.sub(r"^```(json)?|```$", "", (resp.text or "").strip(), flags=re.MULTILINE)
        d = _json.loads(raw)
        return RecallFacts(**{k: d.get(k) for k in RecallFacts().as_dict()})
    except Exception:
        return None


_CLASS_WEIGHT = {"Class I": 0.92, "Class II": 0.7, "Class III": 0.5}


def _refine(exposure: dict[str, Any], facts: RecallFacts) -> dict[str, Any]:
    """Promote a forecast-level exposure to a confirmed-contamination severity."""
    e = dict(exposure)
    confirmed = _CLASS_WEIGHT.get(facts.classification or "", 0.75)
    # a confirmed recall is at least as severe as the document's class weight
    e["severity"] = round(max(float(e.get("severity", 0)), confirmed), 3)
    if e["severity"] >= 0.6 and e.get("status") == "watch":
        e["status"] = "at_risk"
    # recall removes the affected lots from usable cover → recompute $ at risk
    if facts.lots:
        lots_txt = ", ".join(facts.lots)
        daily_rev = float(e.get("monthly_revenue_usd", 0)) / 30.0
        # contaminated lots wipe out part of the runway; model as cover halved
        new_cover = max(0, round(float(e.get("days_of_cover", 0)) / 2))
        disruption = float(e.get("est_disruption_days", 0))
        e["dollars_at_risk_usd"] = round(daily_rev * max(0, disruption - new_cover))
        e["days_of_cover"] = new_cover
        e["rationale"] = (
            f"Confirmed {facts.classification or 'recall'} ({facts.reason or 'contamination'}); "
            f"{len(facts.lots)} affected lots ({lots_txt}) initiated {facts.recall_initiated or 'recently'}, "
            f"distributed to {', '.join(facts.distribution) or 'multiple markets'}. Usable cover halved to "
            f"{new_cover} days against a {int(disruption)}-day disruption."
        )
    return e


@dataclass
class EnrichResult:
    payload: dict[str, Any]      # $defs/ranked_exposures_payload (enriched=true)
    decision: dict[str, Any]     # $defs/decision (kind="enrich")
    facts: dict[str, Any]


def run_enricher(state: RunState, *, pdf_bytes: bytes | None = None, image_path: str | None = None,
                emit: Callable[[str, dict], None] | None = None) -> EnrichResult:
    """Refine severity from a recall document and re-emit ranked_exposures.

    Looks for recall events in the run; if found, extracts facts from the referenced PDF
    (the scripted notice when none is supplied) and refines matching exposures. With no
    recall present it re-emits unchanged (still `enriched:true`) so the contract holds and
    the core loop is never disturbed.
    """
    recall_events = [e for e in state.relevant_events if e.get("event_type") == "recall"]
    exposures = [dict(e) for e in state.exposures]
    facts = RecallFacts()
    refined_ids: list[str] = []
    evidence: list[str] = list(state.all_evidence_event_ids)

    if recall_events:
        doc = pdf_bytes if pdf_bytes is not None else recall_pdf_bytes()
        facts = _llm_extract(doc, image_path) or extract_recall_facts(RECALL_NOTICE_MD)
        recall_suppliers = {h for ev in recall_events for h in (ev.get("supplier_hints") or [])}
        recall_evids = {ev.get("event_id") for ev in recall_events}
        evidence = list(dict.fromkeys(evidence + list(recall_evids)))
        for i, e in enumerate(exposures):
            if (
                e.get("chokepoint_supplier_id") in recall_suppliers
                or e.get("root_cause_event_id") in recall_evids
            ):
                exposures[i] = _refine(e, facts)
                refined_ids.append(e["exposure_id"])

    # re-rank by refined severity
    exposures.sort(key=lambda e: (-(e.get("severity") or 0), e.get("rank", 99)))
    for rank, e in enumerate(exposures, start=1):
        e["rank"] = rank

    payload = {"exposures": exposures, "enriched": True}
    summary = (
        f"Multimodal enrichment of {len(refined_ids)} exposure(s) from recall document"
        + (f" ({facts.classification}, {len(facts.lots)} lots)" if facts.lots else "")
        + "."
        if refined_ids
        else "No recall document in this run; exposures re-emitted unchanged."
    )
    decision = {
        "decision_id": f"dec-enrich-{state.run_id}",
        "run_id": state.run_id,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": AGENT,
        "kind": "enrich",
        "summary": summary,
        "evidence_event_ids": evidence,
        "simulated": state.simulated,
        "related": {"exposure_ids": refined_ids},
    }
    if refined_ids:
        decision["detail"] = "Extracted: " + str(facts.as_dict())
    if emit:
        emit("ranked_exposures", payload)
    return EnrichResult(payload=payload, decision=decision, facts=facts.as_dict())


if __name__ == "__main__":
    import json

    res = run_enricher(enrich_demo_state())
    print(json.dumps(res.payload, indent=2))
    print("\nfacts:", json.dumps(res.facts, indent=2))
    print("decision:", json.dumps(res.decision, indent=2))

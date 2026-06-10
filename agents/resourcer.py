"""Resourcer — find_alternate_suppliers + contingent PO drafting (approval-gated).

Emits `alternates` ($defs/alternates_payload) and `draft_po`
($defs/draft_po_payload). Runs ONLY after the operator approves at the gate.
Recommendation rule: feasible alternates first (effective lead time beats the
days-of-cover runway), then by match score.
"""
from __future__ import annotations

import math
import uuid
from datetime import date, timedelta

from agents import config
from agents.context import RunContext
from agents.schemas import (Alternate, AlternatesPayload, DraftPOPayload, Exposure,
                            ExposurePathsPayload)

AGENT = "resourcer"

# Standing-quote unit prices per component (USD) — demo seed economics; in live
# runs Gemini's negotiation script quotes from these too, so they stay consistent.
UNIT_PRICE_USD = {
    "cmp-emulsifier": 4.85, "cmp-coffee-arabica": 6.20, "cmp-alu-can": 0.18,
    "cmp-pet-film": 2.10, "cmp-oats": 0.92, "cmp-botanical-extract": 14.50,
}
REORDER_BUFFER_DAYS = 7


def _effective_lead(alt: Alternate) -> int:
    return alt.expedited_lead_time_days or alt.lead_time_days


def _round_up(qty: float, step: int = 500) -> float:
    return float(max(step, math.ceil(qty / step) * step))


async def run(ctx: RunContext, top: Exposure, affected: list[Exposure],
              paths_payload: ExposurePathsPayload) -> tuple[AlternatesPayload, DraftPOPayload]:
    disrupted = sorted({p.supplier_chain[0].supplier_id for p in paths_payload.paths})

    out = await ctx.tools.call(
        run_id=ctx.run_id, agent=AGENT, tool="find_alternate_suppliers",
        args={
            "component_id": top.component_id,
            "constraints": {"exclude_supplier_ids": disrupted},
            "size": 5,
        },
        args_summary=f"{top.component_id} · exclude {', '.join(disrupted)}",
    )

    alternates: list[Alternate] = []
    for item in out.get("alternates", []):
        s = item["supplier"]
        alt = Alternate(
            supplier_id=s["supplier_id"], name=s["name"], tier=s.get("tier"),
            location=s["location"], country=s["country"],
            lead_time_days=s["lead_time_days"],
            expedited_lead_time_days=s.get("expedited_lead_time_days"),
            capacity=s["capacity"], certifications=s.get("certifications", []),
            match_score=item["score"],
            est_unit_cost_usd=UNIT_PRICE_USD.get(top.component_id),
        )
        lead = _effective_lead(alt)
        feasible = lead <= top.days_of_cover
        alt.rationale = (
            f"{'Expedited ' if alt.expedited_lead_time_days else ''}lead time {lead} d "
            f"{'beats' if feasible else 'misses'} the {top.days_of_cover:.0f}-day cover runway; "
            f"capacity {alt.capacity}; certifications: {', '.join(alt.certifications) or 'none on file'}."
        )
        alternates.append(alt)

    if not alternates:
        raise RuntimeError(f"no qualified alternates for {top.component_id}")

    alternates.sort(key=lambda a: (_effective_lead(a) <= top.days_of_cover, a.match_score),
                    reverse=True)
    recommended = alternates[0]

    alt_payload = AlternatesPayload(
        exposure_id=top.exposure_id, component_id=top.component_id,
        alternates=alternates, recommended_supplier_id=recommended.supplier_id,
    )
    ctx.bus.agent_emit(ctx.run_id, agent=AGENT, kind="alternates", payload=alt_payload.wire())
    ctx.state["alternates"] = alt_payload.wire()

    # ── contingent PO ────────────────────────────────────────────
    rows = ctx.state.get("_exposure_rows", [])
    daily_consumption = sum(
        r.get("daily_consumption_units") or 0
        for r in rows
        if r["component_id"] == top.component_id
        and r["product_id"] in {e.product_id for e in affected}
    ) or 100.0
    unit = next((r.get("unit") for r in rows if r["component_id"] == top.component_id), None) or "kg"
    quantity = _round_up(daily_consumption * (top.est_disruption_days + REORDER_BUFFER_DAYS))
    unit_price = recommended.est_unit_cost_usd or 5.0
    lead = _effective_lead(recommended)
    expedited = recommended.expedited_lead_time_days is not None and lead < recommended.lead_time_days
    ship_mode = "split" if (expedited and len(affected) > 1) else ("air" if expedited else "sea")
    need_by = (date.today() + timedelta(days=int(top.days_of_cover))).isoformat()
    po_id = f"po-{date.today():%Y}-{uuid.uuid4().hex[:4]}"
    component_name = next(
        (p.component_name for p in paths_payload.paths if p.component_id == top.component_id),
        top.component_id,
    )

    po = DraftPOPayload(
        po_id=po_id, run_id=ctx.run_id, exposure_id=top.exposure_id,
        supplier_id=recommended.supplier_id, supplier_name=recommended.name,
        component_id=top.component_id, component_name=component_name,
        quantity=quantity, unit=unit, unit_price_usd=unit_price,
        total_usd=round(quantity * unit_price, 2),
        incoterms="DAP", ship_mode=ship_mode, need_by_date=need_by,
        lead_time_days=lead, contingent=True, status="draft",
        buyer=config.buyer_name(),
        notes=(
            f"Contingent purchase order triggered by {top.root_cause_event_id}. "
            f"{'Expedited dispatch within the cover window. ' if expedited else ''}"
            f"Becomes binding only on operator approval."
        ),
    )

    pdf = await ctx.tools.call(
        run_id=ctx.run_id, agent=AGENT, tool="generate_po_pdf",
        args=po.wire(),
        args_summary=f"{po_id} → gs://{config.gcs_bucket()}/po/",
    )
    po.pdf_gcs_uri = pdf.get("pdf_gcs_uri")

    ctx.bus.agent_emit(ctx.run_id, agent=AGENT, kind="draft_po", payload=po.wire())
    ctx.state["draft_po"] = po.wire()
    return alt_payload, po

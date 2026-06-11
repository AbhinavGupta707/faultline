"""Assessor — lookup_exposure + severity / days-of-cover / $-at-risk scoring.

Emits `ranked_exposures` ($defs/ranked_exposures_payload).
dollars_at_risk_usd = daily_revenue × max(0, est_disruption_days − days_of_cover).

Deterministic core: per-event-type disruption factors and a severity blend
calibrated against the golden fixtures (the canonical Gujarat-flood case lands
exactly on the contract fixture values: est 21 d, $460k / 0.84, $95k / 0.58).
Gemini (when enabled) refines est_disruption_days and the rationale per
exposure; numbers are recomputed from the refined estimate so the math always
stays self-consistent.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from agents import config
from agents.context import RunContext
from agents.llm import load_prompt
from agents.schemas import (Exposure, ExposurePathsPayload, RankedExposuresPayload,
                            RelevantEvent)

AGENT = "assessor"

# Expected disruption length ≈ factor × severity_raw (days), by event type.
DISRUPTION_FACTOR = {
    "earthquake": 18, "flood": 27, "storm": 10, "hurricane": 18, "wildfire": 14,
    "industrial_accident": 20, "recall": 30, "strike": 12, "port_disruption": 12,
    "drought": 45, "frost": 30, "geopolitical": 30, "other": 14,
}
AT_RISK_GAP_DAYS = 7  # uncovered gap ≥ this → at_risk; any smaller gap → watch


class _Refinement(BaseModel):
    # No Field(gt/lt) here: google-genai's response_schema converter rejects
    # exclusiveMinimum/Maximum. Bounds are clamped in code after the call.
    exposure_id: str
    est_disruption_days: float
    rationale: str


class _RefinementResult(BaseModel):
    items: list[_Refinement]


def est_disruption_days(event: RelevantEvent, scenario) -> float:
    if scenario is not None:
        # what-if: scenario duration plus a magnitude-scaled recovery tail
        return float(round(scenario.duration_days * (1 + 0.5 * scenario.magnitude)))
    return float(round(event.severity_raw * DISRUPTION_FACTOR.get(event.event_type, 14)))


def severity_score(severity_raw: float, gap_days: float, est_days: float) -> float:
    """Blend of raw event severity and the uncovered-gap ratio (fixture-calibrated)."""
    ratio = gap_days / est_days if est_days > 0 else 0.0
    return max(0.0, min(1.0, round(0.75 * severity_raw + 0.6 * ratio - 0.09, 2)))


def _exposure_id(product_id: str, component_id: str) -> str:
    return f"exp-{product_id.removeprefix('prd-')}-{component_id.removeprefix('cmp-')}"


async def run(ctx: RunContext, paths_payload: ExposurePathsPayload,
              primary: RelevantEvent) -> RankedExposuresPayload:
    product_ids = sorted({p.product_id for p in paths_payload.paths})
    component_ids = sorted({p.component_id for p in paths_payload.paths})

    look = await ctx.tools.call(
        run_id=ctx.run_id, agent=AGENT, tool="lookup_exposure",
        args={"product_ids": product_ids, "component_ids": component_ids},
        args_summary=f"{len(product_ids)} products × {len(component_ids)} components",
    )
    rows = {(r["product_id"], r["component_id"]): r for r in look.get("exposures", [])}
    ctx.state["_exposure_rows"] = look.get("exposures", [])  # internal: Resourcer sizes the PO from this

    est = est_disruption_days(primary, ctx.scenario)
    exposures: list[Exposure] = []
    seen: set[tuple[str, str]] = set()
    # when several matched roots reach the same (product, component), the
    # strongest-match root defines the exposure (its supplier is the chokepoint)
    ordered_paths = sorted(paths_payload.paths, key=lambda p: p.match.score, reverse=True)
    for path in ordered_paths:
        key = (path.product_id, path.component_id)
        if key in seen:
            for e in exposures:  # second path into the same exposure
                if e.product_id == path.product_id and e.component_id == path.component_id:
                    e.path_ids.append(path.path_id)
            continue
        row = rows.get(key)
        if row is None:
            continue
        seen.add(key)
        cover = float(row["days_of_cover"])
        gap = max(0.0, est - cover)
        daily_rev = row["monthly_revenue_usd"] / 30
        dollars = float(round(daily_rev * gap))
        sev = severity_score(primary.severity_raw, gap, est)
        status = "at_risk" if gap >= AT_RISK_GAP_DAYS else "watch"
        rationale = (
            f"{cover:.0f} days of {path.component_name} cover against an estimated "
            f"{est:.0f}-day disruption leaves {'a' if gap else 'no'} "
            f"{f'{gap:.0f}-day gap exposed at ~${daily_rev:,.0f}/day' if gap else 'uncovered gap'}; "
            f"root cause: {primary.title}."
        )
        exposures.append(Exposure(
            exposure_id=_exposure_id(path.product_id, path.component_id),
            rank=1,  # re-ranked below
            product_id=path.product_id, product_name=path.product_name,
            component_id=path.component_id,
            root_cause_event_id=primary.event_id,
            chokepoint_supplier_id=path.supplier_chain[0].supplier_id,
            days_of_cover=cover, est_disruption_days=est,
            dollars_at_risk_usd=dollars,
            monthly_revenue_usd=row["monthly_revenue_usd"],
            severity=sev, status=status, rationale=rationale,
            evidence_event_ids=[primary.event_id],
            path_ids=[path.path_id],
            simulated=ctx.simulated,
        ))

    if exposures and ctx.llm.enabled():
        listing = "\n".join(
            f"- {e.exposure_id}: {e.product_name} / {e.component_id}, cover {e.days_of_cover} d, "
            f"daily revenue ${(e.monthly_revenue_usd or 0) / 30:,.0f}, "
            f"deterministic est {e.est_disruption_days} d. Event: {primary.title}"
            for e in exposures
        )
        refined = await ctx.llm.structured(
            model=config.model_pro(),
            system=load_prompt("assessor"),
            prompt=f"Refine disruption estimates for these exposures:\n{listing}",
            schema=_RefinementResult,
        )
        if refined:
            by_id = {r.exposure_id: r for r in refined.items}
            for e in exposures:
                r = by_id.get(e.exposure_id)
                if r is None:
                    continue
                e.est_disruption_days = float(round(min(120.0, max(1.0, r.est_disruption_days))))
                gap = max(0.0, e.est_disruption_days - e.days_of_cover)
                e.dollars_at_risk_usd = float(round((e.monthly_revenue_usd or 0) / 30 * gap))
                e.severity = severity_score(primary.severity_raw, gap, e.est_disruption_days)
                e.status = "at_risk" if gap >= AT_RISK_GAP_DAYS else "watch"
                e.rationale = r.rationale

    exposures.sort(key=lambda e: (e.dollars_at_risk_usd, e.severity), reverse=True)
    for i, e in enumerate(exposures, start=1):
        e.rank = i

    payload = RankedExposuresPayload(exposures=exposures)
    ctx.bus.agent_emit(ctx.run_id, agent=AGENT, kind="ranked_exposures", payload=payload.wire())
    ctx.state["ranked_exposures"] = payload.wire()
    return payload

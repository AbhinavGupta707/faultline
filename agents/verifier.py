"""Verifier — confirms the alternate's lead time beats the runway; residual risk.

Emits `verify_result` ($defs/verify_result_payload).
margin_days = days_of_cover − alternate_lead_time_days (per contract).
"""
from __future__ import annotations

from agents.context import RunContext
from agents.schemas import (Alternate, DraftPOPayload, Exposure, ResidualRisk,
                            StatusChange, VerifyResultPayload)

AGENT = "verifier"


async def run(ctx: RunContext, top: Exposure, affected: list[Exposure],
              po: DraftPOPayload, recommended: Alternate) -> VerifyResultPayload:
    look = await ctx.tools.call(
        run_id=ctx.run_id, agent=AGENT, tool="lookup_exposure",
        args={
            "product_ids": sorted({e.product_id for e in affected}),
            "component_ids": [top.component_id],
        },
        args_summary="re-check cover vs confirmed lead times",
    )
    rows = {(r["product_id"], r["component_id"]): r for r in look.get("exposures", [])}
    row = rows.get((top.product_id, top.component_id))
    cover = float(row["days_of_cover"]) if row else top.days_of_cover

    lead = float(po.lead_time_days)
    margin = round(cover - lead, 1)
    gap_closed = margin >= 0

    factors: list[str] = []
    if len([a for a in (ctx.state.get("alternates", {}).get("alternates") or []) if a]) <= 1:
        factors.append("Single qualified alternate on file for this component")
    if recommended.expedited_lead_time_days is not None:
        factors.append("Expedited freight premium on the first shipment")
    secondary = [e for e in affected if e.exposure_id != top.exposure_id]
    for e in secondary:
        factors.append(
            f"{e.product_name} covered with {max(0.0, e.days_of_cover - lead):.0f} days of slack"
            if e.days_of_cover >= lead else
            f"{e.product_name} still exposed ({e.days_of_cover:.0f} d cover vs {lead:.0f} d lead)"
        )
    if not gap_closed:
        factors.append(
            f"Best alternate lead time ({lead:.0f} d) exceeds the {cover:.0f}-day runway — "
            "consider drawdown rationing or premium logistics"
        )
    if not factors:
        factors.append("No material residual factors identified")

    level = "low" if (gap_closed and margin >= 7) else ("medium" if gap_closed else "high")
    summary = (
        f"Coverage gap {'closed' if gap_closed else 'NOT closed'} for {top.product_name}: "
        f"confirmed {lead:.0f}-day lead vs {cover:.0f} days of cover "
        f"(margin {margin:+.0f} days). Residual risk {level}."
    )

    payload = VerifyResultPayload(
        exposure_id=top.exposure_id, product_id=top.product_id,
        gap_closed=gap_closed, days_of_cover=cover,
        alternate_lead_time_days=lead, margin_days=margin,
        residual_risk=ResidualRisk(level=level, factors=factors),
        status_change=(StatusChange.model_validate({"from": top.status, "to": "secured"})
                       if gap_closed else None),
        summary=summary,
        evidence_event_ids=[top.root_cause_event_id],
    )
    ctx.bus.agent_emit(ctx.run_id, agent=AGENT, kind="verify_result", payload=payload.wire())
    ctx.state["verify_result"] = payload.wire()
    return payload

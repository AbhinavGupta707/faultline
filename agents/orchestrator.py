"""Orchestrator (gemini-3.1-pro tier) — owns the plan, decisions and approval gate.

Drives the canonical plan steps scan → trace → assess → approve → resource →
verify (contracts/ws_protocol.md), narrating every transition. Analysis
(scan/trace/assess) is autonomous; Resourcer onward blocks on approval.decision.
After Verify it iterates agents.depth.DEPTH_AGENTS (Session G's registry,
contracts/components.md §3) — behaviour is identical when the list is empty.
Every stage conclusion is written to the decision-log via write_decision with
evidence_event_ids, then mirrored as ws decision.logged.
"""
from __future__ import annotations

import functools
import inspect
import logging
from typing import Optional

from agents import assessor, negotiator, resourcer, tracer, verifier, watcher
from agents.bus import now_iso
from agents.context import RunContext, short_id
from agents.schemas import (ApprovalContext, ApprovalRequestPayload, Decision,
                            DecisionRelated, Exposure)
from agents import config

log = logging.getLogger("faultline.orchestrator")

AGENT = "orchestrator"

PLAN_STEPS = [
    ("scan", "Scan world events"),
    ("trace", "Trace exposure paths"),
    ("assess", "Quantify exposure"),
    ("approve", "Approval gate"),
    ("resource", "Secure alternate supply"),
    ("verify", "Verify coverage"),
]


class _Plan:
    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.status = {step_id: "pending" for step_id, _ in PLAN_STEPS}

    def update(self, changes: dict[str, str], active: Optional[str]) -> None:
        self.status.update(changes)
        steps = [{"id": sid, "label": label, "status": self.status[sid]}
                 for sid, label in PLAN_STEPS]
        self.ctx.bus.plan_update(self.ctx.run_id, steps, active)

    def finish_skipping(self, done_step: str, skipped: list[str]) -> None:
        changes = {done_step: "done", **{s: "skipped" for s in skipped}}
        self.update(changes, active=None)


async def _log_decision(ctx: RunContext, *, agent: str, kind: str, summary: str,
                        evidence_event_ids: list[str], detail: Optional[str] = None,
                        related: Optional[DecisionRelated] = None) -> None:
    """write_decision (Elastic tool, via Orchestrator) + ws decision.logged."""
    doc = Decision(
        decision_id=ctx.next_decision_id(), run_id=ctx.run_id, ts=now_iso(),
        agent=agent, kind=kind, summary=summary, detail=detail,
        evidence_event_ids=evidence_event_ids, simulated=ctx.simulated,
        related=related,
    ).wire()
    await ctx.tools.call(
        run_id=ctx.run_id, agent=AGENT, tool="write_decision", args=doc,
        args_summary=f"log {kind}: {summary[:60]}",
    )
    ctx.bus.decision_logged(ctx.run_id, doc)


def _final_status(ctx: RunContext, note: str) -> None:
    ctx.bus.status(ctx.run_id, mode=ctx.mode, feeds_ok=True,
                   elastic_ok=True, active_run_id=ctx.run_id, note=note)


async def run_pipeline(ctx: RunContext) -> None:
    ctx.state["run_meta"] = {
        "run_id": ctx.run_id, "mode": ctx.mode, "started_at": now_iso(),
        **({"scenario": ctx.scenario.wire()} if ctx.scenario else {}),
    }
    plan = _Plan(ctx)

    # ── SCAN ─────────────────────────────────────────────────────
    plan.update({"scan": "active"}, active="scan")
    relevant = await watcher.run(ctx)
    events = relevant.events
    considered = relevant.considered_count or len(events)

    if not events:
        await _log_decision(
            ctx, agent=watcher.AGENT, kind="triage",
            summary=f"No supply-chain-relevant events among {considered} fresh world events this cycle.",
            evidence_event_ids=[],
        )
        plan.finish_skipping("scan", ["trace", "assess", "approve", "resource", "verify"])
        _final_status(ctx, "Scan complete — no relevant events this cycle")
        return

    names = " and ".join(e.place_name.split(",")[0] for e in events[:3])
    await _log_decision(
        ctx, agent=watcher.AGENT, kind="triage",
        summary=(f"{len(events)} of {considered} fresh world events are relevant to the "
                 f"supplier graph: {names}."),
        evidence_event_ids=[e.event_id for e in events],
        related=DecisionRelated(
            supplier_ids=sorted({h for e in events for h in e.supplier_hints}) or None),
    )

    # ── TRACE ────────────────────────────────────────────────────
    plan.update({"scan": "done", "trace": "active"}, active="trace")
    primary = tracer.pick_primary(events, ctx.focus_event_id)
    paths_payload = await tracer.run(ctx, events)

    if paths_payload is None:
        await _log_decision(
            ctx, agent=tracer.AGENT, kind="trace",
            summary=(f"No confident supplier match for '{primary.title}' — no exposure "
                     "paths into finished products this cycle."),
            evidence_event_ids=[primary.event_id],
        )
        plan.finish_skipping("trace", ["assess", "approve", "resource", "verify"])
        _final_status(ctx, "Trace complete — no supplier exposure found")
        return

    paths = paths_payload.paths
    chain_suppliers = sorted({n.supplier_id for p in paths for n in p.supplier_chain})
    root = paths[0].supplier_chain[0]
    await _log_decision(
        ctx, agent=tracer.AGENT, kind="trace",
        summary=(f"'{primary.title}' maps to {root.name} (match "
                 f"{paths[0].match.score:.2f}); graph traversal reaches "
                 f"{len({p.product_id for p in paths})} finished product(s) along "
                 f"{len(paths)} path(s)."),
        evidence_event_ids=[primary.event_id],
        related=DecisionRelated(
            supplier_ids=chain_suppliers,
            product_ids=sorted({p.product_id for p in paths}),
            path_ids=[p.path_id for p in paths],
            component_ids=sorted({p.component_id for p in paths}),
        ),
    )

    # ── ASSESS ───────────────────────────────────────────────────
    plan.update({"trace": "done", "assess": "active"}, active="assess")
    ranked = await assessor.run(ctx, paths_payload, primary)
    exposures = ranked.exposures
    top = exposures[0]
    needs_action = [e for e in exposures if e.status == "at_risk" or e.dollars_at_risk_usd > 0]

    await _log_decision(
        ctx, agent=assessor.AGENT, kind="assess",
        summary=(f"{top.product_name} is the critical exposure: {top.days_of_cover:.0f} days of "
                 f"cover vs an estimated {top.est_disruption_days:.0f}-day disruption — "
                 f"${top.dollars_at_risk_usd:,.0f} of revenue at risk."
                 + (f" {len(exposures) - 1} further exposure(s) ranked." if len(exposures) > 1 else "")),
        detail=("dollars_at_risk = daily_revenue × max(0, est_disruption_days − days_of_cover). "
                f"Top severity {top.severity:.2f}."),
        evidence_event_ids=sorted({i for e in exposures for i in e.evidence_event_ids}),
        related=DecisionRelated(
            exposure_ids=[e.exposure_id for e in exposures],
            product_ids=sorted({e.product_id for e in exposures}),
        ),
    )

    if not needs_action:
        plan.finish_skipping("assess", ["approve", "resource", "verify"])
        _final_status(ctx, "Assessment complete — all exposures covered by current inventory")
        return

    # ── APPROVAL GATE (Resourcer onward blocks here) ─────────────
    plan.update({"assess": "done", "approve": "active"}, active="approve")
    approval_id = f"appr-{ctx.run_id.removeprefix('run-')}-{short_id()}"
    dollars_total = sum(e.dollars_at_risk_usd for e in needs_action)
    ctx.approvals.create(approval_id)
    request = ApprovalRequestPayload(
        approval_id=approval_id, action_kind="resource_alternate",
        summary=(f"Re-source {top.component_id.removeprefix('cmp-')} supply for "
                 f"{', '.join(sorted({e.product_name for e in needs_action}))}: draft a contingent "
                 f"PO with the best qualified alternate and confirm availability by call. "
                 f"${dollars_total:,.0f} total at risk if unaddressed."),
        requested_by=AGENT,
        context=ApprovalContext(
            exposure_ids=[e.exposure_id for e in needs_action],
            product_ids=sorted({e.product_id for e in needs_action}),
            component_id=top.component_id,
            dollars_at_risk_total_usd=dollars_total,
            evidence_event_ids=[primary.event_id],
        ),
    )
    ctx.bus.approval_request(ctx.run_id, request.wire())
    approved, note = await ctx.approvals.wait(approval_id, config.approval_timeout_s())

    await _log_decision(
        ctx, agent=AGENT, kind="approval",
        summary=(f"Operator {'approved' if approved else 'rejected'} re-sourcing "
                 f"({approval_id})." + (f" Note: {note}" if note else "")),
        evidence_event_ids=[primary.event_id],
        related=DecisionRelated(approval_id=approval_id,
                                exposure_ids=[e.exposure_id for e in needs_action]),
    )

    if not approved:
        plan.finish_skipping("approve", ["resource", "verify"])
        _final_status(ctx, "Run ended — re-sourcing rejected at the approval gate")
        return

    # ── RESOURCE ─────────────────────────────────────────────────
    plan.update({"approve": "done", "resource": "active"}, active="resource")
    alt_payload, po = await resourcer.run(ctx, top, needs_action, paths_payload)
    recommended = next(a for a in alt_payload.alternates
                       if a.supplier_id == alt_payload.recommended_supplier_id)
    await _log_decision(
        ctx, agent=resourcer.AGENT, kind="resource",
        summary=(f"{recommended.name} selected from {len(alt_payload.alternates)} qualified "
                 f"alternate(s) (match {recommended.match_score:.2f}). Contingent PO {po.po_id} "
                 f"drafted: {po.quantity:,.0f} {po.unit} @ ${po.unit_price_usd}/{po.unit} "
                 f"= ${po.total_usd:,.0f}."),
        evidence_event_ids=[primary.event_id],
        related=DecisionRelated(supplier_ids=[recommended.supplier_id], po_id=po.po_id,
                                exposure_ids=[top.exposure_id],
                                component_ids=[top.component_id]),
    )

    # ── NEGOTIATE (scripted call; in-app voice call is Session E) ─
    call_summary = await negotiator.run(ctx, po, recommended)
    await _log_decision(
        ctx, agent=negotiator.AGENT, kind="negotiate",
        summary=(f"Supplier confirmed on call: {po.quantity:,.0f} {po.unit} within "
                 f"{po.lead_time_days} days at ${po.unit_price_usd}/{po.unit}. "
                 f"Commitment remains contingent on PO status."),
        evidence_event_ids=[primary.event_id],
        related=DecisionRelated(call_id=ctx.state.get("_call", {}).get("call_id"),
                                po_id=po.po_id, supplier_ids=[recommended.supplier_id]),
    )

    # ── VERIFY ───────────────────────────────────────────────────
    plan.update({"resource": "done", "verify": "active"}, active="verify")
    verify_result = await verifier.run(ctx, top, needs_action, po, recommended)
    await _log_decision(
        ctx, agent=verifier.AGENT, kind="verify",
        summary=verify_result.summary,
        evidence_event_ids=verify_result.evidence_event_ids,
        related=DecisionRelated(exposure_ids=[e.exposure_id for e in needs_action],
                                product_ids=sorted({e.product_id for e in needs_action})),
    )
    plan.update({"verify": "done"}, active=None)

    # ── DEPTH AGENTS (Session G registry — must never block the core) ──
    await _run_depth_agents(ctx)

    secured = "secured" if verify_result.gap_closed else "NOT closed"
    _final_status(ctx, (f"Run complete — top exposure {secured}, "
                        f"${top.dollars_at_risk_usd:,.0f} at risk addressed"))


_DEPTH_KIND_TO_AGENT = {"brief": "briefer", "ranked_exposures": "enricher"}


async def _run_depth_agents(ctx: RunContext) -> None:
    """Run Session G's depth lane with the shared session state; never blocks
    or breaks the core loop. Preferred path (per agents/depth/HANDOFF.md):
    `agents.depth.run_all_depth(state, emit)` — Briefer→Enricher→BQExport with
    every emission narrated through our bus; afterwards any decisions G buffered
    on state["_decisions"] are written to the decision-log and mirrored on the
    WS. Fallback: duck-typed iteration of DEPTH_AGENTS. With the phase0-empty
    registry both paths are no-ops."""
    import asyncio

    try:
        import agents.depth as depth
    except Exception as exc:  # registry must never break the core loop
        log.warning("depth registry import failed: %s", exc)
        return
    run_all = getattr(depth, "run_all_depth", None)
    registry = getattr(depth, "DEPTH_AGENTS", []) or []
    if run_all is None and not registry:
        return

    loop = asyncio.get_running_loop()

    def _emit_threadsafe(kind: str, payload: dict) -> None:
        loop.call_soon_threadsafe(functools.partial(
            ctx.bus.agent_emit, ctx.run_id,
            agent=_DEPTH_KIND_TO_AGENT.get(kind, "depth"), kind=kind, payload=payload))

    ctx.state["_run_id"] = ctx.run_id
    ctx.state["_tools"] = ctx.tools

    if run_all is not None:
        try:
            # G's tasks are sync (BQ/GCS I/O) — keep the event loop (and WS) alive.
            await asyncio.to_thread(run_all, ctx.state, _emit_threadsafe)
        except Exception as exc:  # run_all_depth contains its own failures, but be safe
            log.exception("run_all_depth failed (contained): %s", exc)
    else:
        for agent in registry:
            name = getattr(agent, "name", agent.__class__.__name__)
            try:
                runner = getattr(agent, "run", None)
                result = runner(ctx.state) if callable(runner) else (
                    agent(ctx.state) if callable(agent) else None)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                log.exception("depth agent %s failed (contained): %s", name, exc)

    # write G's buffered decisions (kinds brief/enrich) through the narrated path
    for doc in ctx.state.get("_decisions", []) or []:
        try:
            doc.setdefault("run_id", ctx.run_id)
            doc.setdefault("ts", now_iso())
            doc.setdefault("decision_id", ctx.next_decision_id())
            doc.setdefault("simulated", ctx.simulated)
            await ctx.tools.call(
                run_id=ctx.run_id, agent=AGENT, tool="write_decision", args=doc,
                args_summary=f"log {doc.get('kind', 'depth')}: {str(doc.get('summary', ''))[:60]}",
            )
            ctx.bus.decision_logged(ctx.run_id, doc)
        except Exception as exc:
            log.exception("depth decision write failed (contained): %s", exc)

"""Tracer — match_event_to_suppliers + traverse_supply_graph (gemini-3.1-pro tier).

Emits `exposure_paths` ($defs/exposure_paths_payload) for the PRIMARY event of
the cycle (highest severity; the focus event on what-if runs). Other relevant
events stay visible as watch items in relevant_events and get their own cycle
when the control loop next polls — one dominant disruption per run keeps the
narration (and the map) legible.
"""
from __future__ import annotations

from typing import Optional

from agents.context import RunContext
from agents.schemas import (ChainNode, ExposurePath, ExposurePathsPayload, PathMatch,
                            RelevantEvent)

AGENT = "tracer"
MATCH_THRESHOLD = 0.5  # contract: ≥0.5 = confident match
MAX_HOPS = 4


def pick_primary(events: list[RelevantEvent], focus_event_id: Optional[str]) -> RelevantEvent:
    if focus_event_id:
        for e in events:
            if e.event_id == focus_event_id:
                return e
    return max(events, key=lambda e: e.severity_raw)


def _path_id(component_id: str, product_id: str) -> str:
    return f"path-{component_id.removeprefix('cmp-')}-{product_id.removeprefix('prd-')}"


async def run(ctx: RunContext, events: list[RelevantEvent]) -> Optional[ExposurePathsPayload]:
    primary = pick_primary(events, ctx.focus_event_id)
    event_text = f"{primary.title}. {primary.why_relevant}"

    match_out = await ctx.tools.call(
        run_id=ctx.run_id, agent=AGENT, tool="match_event_to_suppliers",
        args={
            "event_text": event_text, "event_id": primary.event_id,
            "lat": primary.location.lat, "lon": primary.location.lon, "radius_km": 500,
        },
        args_summary=f"{primary.place_name} {primary.event_type} text · r=500 km",
    )
    confident = [m for m in match_out.get("matches", []) if m["score"] >= MATCH_THRESHOLD]
    if not confident:
        return None

    supplier_ids = [m["supplier"]["supplier_id"] for m in confident]
    by_id = {m["supplier"]["supplier_id"]: m for m in confident}

    trav = await ctx.tools.call(
        run_id=ctx.run_id, agent=AGENT, tool="traverse_supply_graph",
        args={"supplier_ids": supplier_ids, "max_hops": MAX_HOPS},
        args_summary=f"from {supplier_ids[0]} · max {MAX_HOPS} hops",
    )

    paths = []
    for p in trav.get("paths", []):
        root = p["root_supplier_id"]
        m = by_id.get(root, confident[0])
        signals = m.get("signals", {})
        dist = signals.get("geo_distance_km")
        rationale = (f"Event text matches the supplier profile (hybrid score {m['score']:.2f})"
                     + (f"; site {dist} km from the event centroid." if dist is not None else "."))
        paths.append(ExposurePath(
            path_id=_path_id(p["component_id"], p["product_id"]),
            event_id=primary.event_id,
            supplier_chain=[ChainNode.model_validate(n) for n in p["supplier_chain"]],
            component_id=p["component_id"],
            component_name=p.get("component_name") or p["component_id"],
            product_id=p["product_id"],
            product_name=p.get("product_name") or p["product_id"],
            hops=p["hops"],
            match=PathMatch(score=m["score"], method="hybrid_bm25_elser", rationale=rationale),
        ))
    if not paths:
        return None

    payload = ExposurePathsPayload(event_id=primary.event_id, paths=paths)
    ctx.bus.agent_emit(ctx.run_id, agent=AGENT, kind="exposure_paths", payload=payload.wire())
    ctx.state["exposure_paths"] = payload.wire()
    return payload

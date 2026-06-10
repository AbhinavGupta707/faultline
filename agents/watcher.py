"""Watcher — search_events + Gemini triage of the feed batch (gemini-3.5-flash).

Emits `relevant_events` ($defs/relevant_events_payload). Deterministic core:
severity-threshold triage with templated why_relevant; Gemini (when enabled)
rewrites why_relevant and adds supplier_hints per event.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel

from agents import config
from agents.context import RunContext
from agents.llm import load_prompt
from agents.schemas import RelevantEvent, RelevantEventsPayload, TimeWindow, WorldEvent

AGENT = "watcher"
SEVERITY_THRESHOLD = 0.5
MAX_RELEVANT = 5
WINDOW_MINUTES = 60


class _TriageItem(BaseModel):
    event_id: str
    relevant: bool
    why_relevant: str
    supplier_hints: list[str] = []


class _TriageResult(BaseModel):
    items: list[_TriageItem]


def _template_why(e: WorldEvent) -> str:
    return (f"{e.event_type.replace('_', ' ').capitalize()} near {e.place_name} "
            f"(severity {e.severity_raw:.2f}) sits in a region with active suppliers "
            f"in the company's graph and may interrupt production or logistics.")


async def run(ctx: RunContext) -> RelevantEventsPayload:
    now = datetime.now(timezone.utc)
    window_from = (now - timedelta(minutes=WINDOW_MINUTES)).isoformat(timespec="seconds").replace("+00:00", "Z")
    args: dict = {
        "query": "supply chain disruption near supplier regions",
        "include_simulated": ctx.simulated,
        "size": 50,
    }
    if not ctx.simulated and config.elastic_mode() == "live":
        # live cadence scans a sliding window; what-if must see the synthetic event.
        # (The mock's fixture set IS the canonical "last hour" batch — no window.)
        args["from"] = window_from
    out = await ctx.tools.call(
        run_id=ctx.run_id, agent=AGENT, tool="search_events", args=args,
        args_summary=f"events last {WINDOW_MINUTES} min near supplier regions",
    )
    events = [WorldEvent.model_validate(e) for e in out.get("events", [])]
    considered = len(events)

    if ctx.simulated and ctx.focus_event_id:
        chosen = [e for e in events if e.id == ctx.focus_event_id]
    else:
        chosen = [
            e for e in events
            if not e.simulated
            and e.id not in ctx.exclude_event_ids
            and e.severity_raw >= SEVERITY_THRESHOLD
        ][:MAX_RELEVANT]

    why: dict[str, str] = {e.id: _template_why(e) for e in chosen}
    hints: dict[str, list[str]] = {e.id: [] for e in chosen}

    if chosen and ctx.llm.enabled():
        listing = "\n".join(
            f"- {e.id}: [{e.event_type}] {e.title} @ {e.place_name} (severity {e.severity_raw})"
            for e in events
        )
        triage = await ctx.llm.structured(
            model=config.model_flash(),
            system=load_prompt("watcher"),
            prompt=f"Triage these world events for supply-chain relevance:\n{listing}",
            schema=_TriageResult,
        )
        if triage:
            llm_items = {i.event_id: i for i in triage.items if i.relevant}
            for e in chosen:
                if e.id in llm_items:
                    why[e.id] = llm_items[e.id].why_relevant
                    hints[e.id] = llm_items[e.id].supplier_hints

    payload = RelevantEventsPayload(
        events=[
            RelevantEvent(
                event_id=e.id, title=e.title, source=e.source, event_type=e.event_type,
                severity_raw=e.severity_raw, location=e.location, place_name=e.place_name,
                published_at=e.published_at, url=e.url or None, simulated=e.simulated,
                why_relevant=why[e.id], supplier_hints=hints[e.id],
            )
            for e in chosen
        ],
        considered_count=considered,
        window=TimeWindow.model_validate({"from": window_from,
                                          "to": now.isoformat(timespec="seconds").replace("+00:00", "Z")}),
    )
    ctx.bus.agent_emit(ctx.run_id, agent=AGENT, kind="relevant_events", payload=payload.wire())
    ctx.state["relevant_events"] = payload.wire()
    return payload

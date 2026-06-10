"""Negotiator — drafts and runs the scripted supplier confirmation call.

Emits `call_event` payloads ($defs/call_event_payload): status → transcript
beats → summary → status ended. The deterministic script is templated from the
PO; Gemini (gemini-3.5-flash) writes a richer script when enabled. The audible
in-app voice call is Session E's voice_gateway — this agent produces the same
payload shapes, so the UI treats both identically. The agent always
self-identifies as an AI and every commitment stays contingent on PO approval.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from pydantic import BaseModel

from agents import config
from agents.context import RunContext
from agents.llm import load_prompt
from agents.schemas import Alternate, CallEventPayload, CallSummary, DraftPOPayload

AGENT = "negotiator"


class _ScriptLine(BaseModel):
    speaker: Literal["faultline_agent", "supplier"]
    text: str


class _CallScript(BaseModel):
    lines: list[_ScriptLine]


def _template_script(po: DraftPOPayload, alt: Alternate) -> list[_ScriptLine]:
    qty = f"{po.quantity:,.0f} {po.unit}"
    price = f"${po.unit_price_usd:.2f} per {po.unit}"
    return [
        _ScriptLine(speaker="faultline_agent", text=(
            f"Good afternoon — this is Faultline, the AI procurement agent calling on behalf of "
            f"{po.buyer or 'our client'} about {po.component_name} supply. Our primary source is "
            f"disrupted, and we'd like to confirm the availability you quoted."
        )),
        _ScriptLine(speaker="supplier", text=(
            f"Hello Faultline, this is {po.supplier_name} order desk. Yes — we hold stock of "
            f"{po.component_name}. {qty} is available as quoted."
        )),
        _ScriptLine(speaker="faultline_agent", text=(
            f"We need delivery within {po.lead_time_days} days against a contingent purchase order "
            f"{po.po_id}. Can you commit to dispatch at the quoted {price}?"
        )),
        _ScriptLine(speaker="supplier", text=(
            f"Confirmed. {qty} dispatching within {po.lead_time_days} days, and we will hold "
            f"{price} for this order."
        )),
    ]


async def run(ctx: RunContext, po: DraftPOPayload, alt: Alternate) -> CallSummary:
    call_id = f"call-{uuid.uuid4().hex[:8]}"
    delay = config.narration_delay_s()

    async def emit(payload: CallEventPayload) -> None:
        ctx.bus.agent_emit(ctx.run_id, agent=AGENT, kind="call_event", payload=payload.wire())
        if delay:
            await asyncio.sleep(delay)

    await emit(CallEventPayload(call_id=call_id, event="status", status="initiating"))

    lines = _template_script(po, alt)
    if ctx.llm.enabled():
        script = await ctx.llm.structured(
            model=config.model_flash(),
            system=load_prompt("negotiator"),
            prompt=(
                f"Draft a 4-6 line supplier confirmation call for PO {po.po_id}: "
                f"{po.quantity:,.0f} {po.unit} of {po.component_name} from {po.supplier_name} "
                f"at ${po.unit_price_usd}/{po.unit}, needed within {po.lead_time_days} days "
                f"(need-by {po.need_by_date}). The agent opens by self-identifying as an AI; "
                f"the supplier confirms availability, dates and price."
            ),
            schema=_CallScript,
        )
        if script and script.lines:
            lines = script.lines

    await emit(CallEventPayload(call_id=call_id, event="status", status="connected"))
    for line in lines:
        await emit(CallEventPayload(call_id=call_id, event="transcript",
                                    speaker=line.speaker, text=line.text, is_final=True))

    summary = CallSummary(
        agreed=True,
        lead_time_days=po.lead_time_days,
        expedited_lead_time_days=alt.expedited_lead_time_days,
        quantity=po.quantity,
        unit_price_usd=po.unit_price_usd,
        notes=(
            f"Supplier confirmed {po.quantity:,.0f} {po.unit} within {po.lead_time_days} days at "
            f"${po.unit_price_usd}/{po.unit}. Agent self-identified as AI; commitment contingent "
            f"on PO approval ({po.po_id})."
        ),
    )
    await emit(CallEventPayload(call_id=call_id, event="summary", summary=summary))
    await emit(CallEventPayload(call_id=call_id, event="status", status="ended"))
    ctx.state["_call"] = {"call_id": call_id, "summary": summary.wire()}
    return summary

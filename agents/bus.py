"""The narration bus — EVERYTHING the agents do flows through here to the WS.

The UI's life depends on this: every plan step, tool call (Elastic-flagged),
agent emission, decision and approval request is published as a contract-shaped
message (contracts/ws_protocol.md). `seq` is assigned per WS connection at send
time (the envelope's seq is "monotonic per connection"), so the bus stores
seq-less messages and fans them out to subscriber queues.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

HISTORY_LIMIT = 2000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Bus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self.history: deque[dict] = deque(maxlen=HISTORY_LIMIT)

    # ── plumbing ────────────────────────────────────────────────
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, type_: str, run_id: Optional[str], payload: dict[str, Any]) -> dict:
        msg = {"type": type_, "ts": now_iso(), "run_id": run_id, "payload": payload}
        self.history.append(msg)
        for q in list(self._subscribers):
            q.put_nowait(msg)
        return msg

    def run_history(self, run_id: str) -> list[dict]:
        """Messages of one run (so a client reconnecting mid-run can catch up)."""
        return [m for m in self.history if m["run_id"] == run_id]

    # ── typed helpers (one per server→client message type) ─────
    def status(self, run_id: Optional[str], *, mode: str, feeds_ok: bool, elastic_ok: bool,
               active_run_id: Optional[str] = None, note: Optional[str] = None) -> dict:
        payload: dict[str, Any] = {
            "mode": mode, "feeds_ok": feeds_ok, "elastic_ok": elastic_ok,
            "active_run_id": active_run_id,
        }
        if note is not None:
            payload["note"] = note
        return self.publish("status", run_id, payload)

    def plan_update(self, run_id: str, steps: list[dict], active_step: Optional[str]) -> dict:
        return self.publish("plan.update", run_id, {"steps": steps, "active_step": active_step})

    def tool_call(self, run_id: str, *, call_id: str, agent: str, tool: str,
                  args_summary: str, status: str, elastic: bool,
                  latency_ms: Optional[float] = None, error: Optional[str] = None) -> dict:
        payload: dict[str, Any] = {
            "call_id": call_id, "agent": agent, "tool": tool,
            "args_summary": args_summary, "status": status, "elastic": elastic,
        }
        if latency_ms is not None:
            payload["latency_ms"] = round(latency_ms, 1)
        if error is not None:
            payload["error"] = error
        return self.publish("tool.call", run_id, payload)

    def agent_emit(self, run_id: str, *, agent: str, kind: str, payload: dict) -> dict:
        return self.publish("agent.emit", run_id, {"agent": agent, "kind": kind, "payload": payload})

    def decision_logged(self, run_id: str, decision: dict) -> dict:
        return self.publish("decision.logged", run_id, decision)

    def approval_request(self, run_id: str, payload: dict) -> dict:
        return self.publish("approval.request", run_id, payload)

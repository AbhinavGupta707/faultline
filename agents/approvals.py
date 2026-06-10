"""Approval gate plumbing — Resourcer onward blocks on approval.decision.

One registry per app. A run awaits `wait()`; the decision arrives from
POST /approval, a ws `approval.decision`, or a `voice.intent` approve/reject —
all funnel into `resolve()`. Idempotent per approval_id: the first decision
wins; later ones return applied=False (contracts/http_api.md).
"""
from __future__ import annotations

import asyncio
from typing import Optional


class ApprovalRegistry:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}
        self._decided: dict[str, tuple[bool, Optional[str]]] = {}

    def create(self, approval_id: str) -> None:
        self._pending[approval_id] = asyncio.get_running_loop().create_future()

    def pending_ids(self) -> list[str]:
        return [a for a, f in self._pending.items() if not f.done()]

    def resolve(self, approval_id: str, approved: bool, note: Optional[str] = None) -> bool:
        """Returns applied=False if the approval is unknown or already decided."""
        fut = self._pending.get(approval_id)
        if fut is None or fut.done():
            return False
        self._decided[approval_id] = (approved, note)
        fut.set_result((approved, note))
        return True

    async def wait(self, approval_id: str, timeout_s: float) -> tuple[bool, Optional[str]]:
        """Blocks until decided; a timeout counts as a rejection (safe default)."""
        fut = self._pending[approval_id]
        try:
            return await asyncio.wait_for(fut, timeout=timeout_s)
        except asyncio.TimeoutError:
            self._decided[approval_id] = (False, "approval timed out — defaulting to rejected")
            return False, "approval timed out — defaulting to rejected"
        finally:
            self._pending.pop(approval_id, None)

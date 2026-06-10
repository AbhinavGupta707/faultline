"""GDELT 2.0 Doc API — JSON, highest value & messiest. Build step 5.

Relevance-filtered with cheap heuristics before writing (Gemini triage is downstream
in the Watcher, not here).
"""
from __future__ import annotations

import httpx


async def fetch(client: httpx.AsyncClient) -> dict:  # pragma: no cover - until step 5
    raise NotImplementedError("gdelt source not yet implemented")


def parse(raw: dict) -> list[dict]:
    return []

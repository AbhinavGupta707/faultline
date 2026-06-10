"""openFDA food enforcement (recalls) — JSON. Implemented in build step 2."""
from __future__ import annotations

import httpx

_PENDING = True


async def fetch(client: httpx.AsyncClient) -> dict:  # pragma: no cover - until step 2
    raise NotImplementedError("openfda source not yet implemented")


def parse(raw: dict) -> list[dict]:
    return []

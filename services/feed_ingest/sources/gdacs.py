"""GDACS global disasters — RSS/XML. Build step 4."""
from __future__ import annotations

import httpx


async def fetch(client: httpx.AsyncClient) -> str:  # pragma: no cover - until step 4
    raise NotImplementedError("gdacs source not yet implemented")


def parse(raw: str) -> list[dict]:
    return []

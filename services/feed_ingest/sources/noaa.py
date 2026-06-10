"""NOAA/NWS active alerts — GeoJSON (needs a User-Agent). Build step 3."""
from __future__ import annotations

import httpx


async def fetch(client: httpx.AsyncClient) -> dict:  # pragma: no cover - until step 3
    raise NotImplementedError("noaa source not yet implemented")


def parse(raw: dict) -> list[dict]:
    return []

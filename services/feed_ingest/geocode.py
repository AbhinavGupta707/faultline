"""Geocoding for sources that ship place text but no coordinates (openFDA, GDELT).

Calls the Google Maps Geocoding REST API directly (no dedicated service — impl plan
§2 dropped services/geocode). Results are cached in-process for the lifetime of the
container so a 5-minute scheduler tick re-geocodes the same firm cities for free.

`geocode()` returns None on any miss/error rather than raising — a feed item with no
resolvable location is simply dropped upstream, never half-written.
"""
from __future__ import annotations

import os

import httpx

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_cache: dict[str, tuple[float, float] | None] = {}


async def geocode(
    client: httpx.AsyncClient, query: str
) -> tuple[float, float] | None:
    """Resolve free-text place → (lat, lon). Cached; None on miss."""
    key = (query or "").strip().lower()
    if not key:
        return None
    if key in _cache:
        return _cache[key]

    api_key = os.getenv("MAPS_API_KEY")
    if not api_key:
        _cache[key] = None
        return None

    try:
        resp = await client.get(
            _GEOCODE_URL,
            params={"address": query, "key": api_key},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if data.get("status") == "OK" and results:
            loc = results[0]["geometry"]["location"]
            out = (float(loc["lat"]), float(loc["lng"]))
            _cache[key] = out
            return out
    except (httpx.HTTPError, KeyError, ValueError):
        pass
    _cache[key] = None
    return None

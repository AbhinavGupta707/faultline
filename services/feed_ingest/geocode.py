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

from common import region_for

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


async def resolve_locations(
    client: httpx.AsyncClient, docs: list[dict]
) -> tuple[list[dict], int]:
    """Fill `location`+`region` on any doc carrying `_geo_query` instead of coords.

    Docs that already have `location` (USGS/NOAA/GDACS) pass through untouched. Docs
    whose place text can't be geocoded are DROPPED — a world_event without a location
    is unmatchable and the schema requires it. Returns (writable_docs, dropped).
    """
    out: list[dict] = []
    dropped = 0
    for doc in docs:
        if "location" in doc:
            doc.pop("_geo_query", None)
            out.append(doc)
            continue
        query = doc.pop("_geo_query", None)
        coords = await geocode(client, query) if query else None
        if coords is None:
            dropped += 1
            continue
        lat, lon = coords
        doc["location"] = {"lat": round(lat, 5), "lon": round(lon, 5)}
        doc.setdefault("region", region_for(lat, lon))
        out.append(doc)
    return out, dropped

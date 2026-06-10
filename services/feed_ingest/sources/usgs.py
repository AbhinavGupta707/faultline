"""USGS earthquakes — all_hour.geojson (the 20-minute win).

Feed: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson
Trivial GeoJSON FeatureCollection. Every feature is an earthquake with a Point
geometry [lon, lat, depth_km] and rich `properties`.
"""
from __future__ import annotations

import httpx

from common import iso_from_epoch_ms, make_event

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"


async def fetch(client: httpx.AsyncClient) -> dict:
    resp = await client.get(FEED_URL, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


def _severity(mag: float | None) -> float:
    """Magnitude → [0,1]. M0→0, M10→1 (linear); negatives clamp to 0.

    A coarse but monotonic and honest scale; the downstream Gemini triage refines
    relevance, this just gives the firehose a sortable magnitude proxy.
    """
    if mag is None:
        return 0.0
    return mag / 10.0


def parse(raw: dict) -> list[dict]:
    events: list[dict] = []
    for feat in raw.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue  # no usable location → unmatchable, drop
        lon, lat = float(coords[0]), float(coords[1])
        mag = props.get("mag")
        depth_km = coords[2] if len(coords) > 2 else None
        place = props.get("place") or "Unknown location"
        title = props.get("title") or place
        ts = props.get("time")
        published_at = iso_from_epoch_ms(ts) if ts else None
        if published_at is None:
            continue

        bits = []
        if mag is not None:
            bits.append(f"Magnitude {mag} earthquake")
        bits.append(f"located {place}")
        if depth_km is not None:
            bits.append(f"at {depth_km:g} km depth")
        if props.get("tsunami"):
            bits.append("— tsunami evaluation in effect")
        summary = " ".join(bits) + "."

        fid = feat.get("id") or props.get("code") or f"{lat},{lon},{ts}"
        events.append(
            make_event(
                id=f"usgs-{fid}",
                source="usgs",
                title=title,
                event_type="earthquake",
                lat=lat,
                lon=lon,
                place_name=place,
                severity_raw=_severity(mag),
                published_at=published_at,
                summary=summary,
                url=props.get("url"),
            )
        )
    return events

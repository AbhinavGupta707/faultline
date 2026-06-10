"""NOAA / NWS active alerts — GeoJSON.

Feed: https://api.weather.gov/alerts/active  (a descriptive User-Agent is required;
main.py sets one on the shared client).

Alerts carry either a Polygon/MultiPolygon geometry (we use its centroid) or null
geometry (we defer to geocoding the areaDesc). We keep only consequential, current
alerts — the firehose of Minor advisories is noise the control tower doesn't need.
"""
from __future__ import annotations

import httpx

from common import iso_to_utc, make_event

FEED_URL = "https://api.weather.gov/alerts/active"

# NWS severity → severity_raw.
_SEVERITY = {
    "Extreme": 0.95,
    "Severe": 0.75,
    "Moderate": 0.5,
    "Minor": 0.3,
    "Unknown": 0.4,
}

# Keep only these severities — Minor/Unknown advisories are dropped as noise.
_KEEP_SEVERITIES = {"Extreme", "Severe", "Moderate"}

# NWS `event` free text → our event_type enum (first matching keyword wins).
_TYPE_KEYWORDS = [
    ("flood", "flood"),
    ("hurricane", "hurricane"),
    ("typhoon", "hurricane"),
    ("tropical storm", "storm"),
    ("tornado", "storm"),
    ("thunderstorm", "storm"),
    ("winter storm", "storm"),
    ("blizzard", "storm"),
    ("snow", "storm"),
    ("ice storm", "storm"),
    ("storm", "storm"),
    ("fire", "wildfire"),
    ("red flag", "wildfire"),
    ("heat", "drought"),
    ("drought", "drought"),
    ("freeze", "frost"),
    ("frost", "frost"),
]


def _event_type(event_text: str) -> str:
    low = (event_text or "").lower()
    for kw, etype in _TYPE_KEYWORDS:
        if kw in low:
            return etype
    return "other"


def _centroid(geometry: dict | None) -> tuple[float, float] | None:
    """Average vertex of a (Multi)Polygon exterior ring → (lat, lon)."""
    if not geometry:
        return None
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return None
    if gtype == "Polygon":
        ring = coords[0]
    elif gtype == "MultiPolygon":
        ring = coords[0][0]
    elif gtype == "Point":
        return (float(coords[1]), float(coords[0]))
    else:
        return None
    if not ring:
        return None
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


async def fetch(client: httpx.AsyncClient) -> dict:
    resp = await client.get(FEED_URL, timeout=25.0)
    resp.raise_for_status()
    return resp.json()


def parse(raw: dict) -> list[dict]:
    events: list[dict] = []
    for feat in raw.get("features", []):
        props = feat.get("properties") or {}
        if props.get("status") != "Actual":
            continue
        if props.get("messageType") == "Cancel":
            continue
        severity = props.get("severity") or "Unknown"
        if severity not in _KEEP_SEVERITIES:
            continue

        urn = props.get("id") or feat.get("id")
        if not urn:
            continue
        published_at = iso_to_utc(props.get("sent") or props.get("effective"))
        if published_at is None:
            continue

        event_text = props.get("event") or "Weather alert"
        area = props.get("areaDesc") or "United States"
        title = props.get("headline") or f"{event_text} — {area}"
        desc = (props.get("description") or "").strip().replace("\n", " ")
        instruction = (props.get("instruction") or "").strip().replace("\n", " ")
        summary = " | ".join(s for s in (desc[:400], instruction[:200]) if s) or None

        kwargs = dict(
            id=f"noaa-{urn}",
            source="noaa",
            title=title,
            event_type=_event_type(event_text),
            place_name=area,
            severity_raw=_SEVERITY.get(severity, 0.4),
            published_at=published_at,
            summary=summary,
            url=feat.get("id"),
        )
        centroid = _centroid(feat.get("geometry"))
        if centroid is not None:
            kwargs["lat"], kwargs["lon"] = centroid
        else:
            # No polygon — geocode the first named area segment.
            kwargs["geo_query"] = area.split(";")[0].strip()
        events.append(make_event(**kwargs))
    return events

"""Shared normalization helpers for every feed source.

Output spec is `$defs/world_event` in contracts/schemas/faultline.schema.json:
required = id, source, title, event_type, location{lat,lon}, place_name, region,
severity_raw (0..1), published_at (ISO date-time), simulated. Optional = summary, url.

All normalizers funnel through `make_event` so the doc shape, field pruning, and the
`severity_raw` clamp are enforced in exactly one place.
"""
from __future__ import annotations

from datetime import datetime, timezone

# event_type enum mirrors $defs/event_type — keep in sync with the contract.
EVENT_TYPES = {
    "earthquake", "flood", "storm", "hurricane", "wildfire", "industrial_accident",
    "recall", "strike", "port_disruption", "drought", "frost", "geopolitical", "other",
}

SOURCES = {"usgs", "noaa", "gdacs", "openfda", "gdelt"}


def clamp01(x: float) -> float:
    """Clamp to [0,1] — severity_raw must always land in range."""
    return 0.0 if x < 0 else 1.0 if x > 1 else float(x)


def normalize_severity(value: float, lo: float, hi: float) -> float:
    """Linear-scale a raw source metric into [0,1]. lo→0, hi→1, clamped."""
    if hi <= lo:
        return 0.0
    return clamp01((value - lo) / (hi - lo))


def iso_from_epoch_ms(ms: int | float) -> str:
    """USGS/GDELT-style epoch milliseconds → ISO-8601 UTC (Z)."""
    return (
        datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def iso_to_utc(s: str | None) -> str | None:
    """Normalize an offset-aware ISO string (e.g. '...-05:00') to UTC 'Z'.

    Returns None on anything unparseable. Naive timestamps are assumed UTC.
    """
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# Coarse continental buckets keyed off lat/lon. First box that contains the point
# wins, so order encodes precedence (the Americas before the rest, sub-regions of
# Asia before the broad fallbacks). Vocabulary matches the golden fixtures
# (south-asia, southeast-asia, north-america, latam) and extends it consistently.
_REGION_BOXES = [
    # name, lat_min, lat_max, lon_min, lon_max
    ("north-america", 15.0, 72.0, -170.0, -50.0),
    ("latam", -56.0, 15.0, -120.0, -30.0),
    ("south-asia", 5.0, 38.0, 60.0, 92.0),
    ("east-asia", 18.0, 54.0, 100.0, 146.0),
    ("southeast-asia", -11.0, 28.0, 92.0, 141.0),
    ("oceania", -50.0, -11.0, 110.0, 180.0),
    ("oceania", -50.0, -11.0, -180.0, -130.0),  # Pacific side of the antimeridian (Fiji/Tonga)
    ("middle-east", 12.0, 42.0, 34.0, 63.0),
    ("central-asia", 35.0, 55.0, 46.0, 87.0),
    ("europe", 36.0, 72.0, -25.0, 40.0),
    ("africa", -36.0, 36.0, -20.0, 52.0),
]


def region_for(lat: float, lon: float) -> str:
    """Bucket a coordinate into a coarse region keyword. Falls back to 'other'."""
    for name, la0, la1, lo0, lo1 in _REGION_BOXES:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return "other"


def make_event(
    *,
    id: str,
    source: str,
    title: str,
    event_type: str,
    place_name: str,
    severity_raw: float,
    published_at: str,
    lat: float | None = None,
    lon: float | None = None,
    geo_query: str | None = None,
    summary: str | None = None,
    url: str | None = None,
    region: str | None = None,
    simulated: bool = False,
) -> dict:
    """Assemble a contract-valid `world_event` doc.

    Pass `lat`/`lon` when the source carries coordinates (USGS/NOAA/GDACS). When it
    only carries place *text* (openFDA/GDELT), omit them and pass `geo_query`: the doc
    is returned with a private `_geo_query` and NO `location`, to be resolved by
    `geocode.resolve_locations` before it can be written.

    `event_semantic` is intentionally NOT set — the semantic_text mapping populates
    it server-side on ingest. Optional empty fields are pruned so docs stay tidy.
    """
    if event_type not in EVENT_TYPES:
        event_type = "other"
    doc = {
        "id": id,
        "source": source,
        "title": title.strip(),
        "event_type": event_type,
        "place_name": place_name.strip(),
        "severity_raw": round(clamp01(severity_raw), 4),
        "published_at": published_at,
        "simulated": simulated,
    }
    if lat is not None and lon is not None:
        doc["location"] = {"lat": round(float(lat), 5), "lon": round(float(lon), 5)}
        doc["region"] = region or region_for(lat, lon)
    else:
        # Geo deferred — resolve_locations fills location+region (or drops the doc).
        doc["_geo_query"] = (geo_query or place_name).strip()
        if region:
            doc["region"] = region
    if summary and summary.strip():
        doc["summary"] = summary.strip()
    if url and url.strip():
        doc["url"] = url.strip()
    return doc

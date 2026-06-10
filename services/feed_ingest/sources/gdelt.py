"""GDELT 2.0 Doc API — JSON. Highest value, messiest; built last.

Feed: https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=artlist&format=json

`artlist` returns article metadata (title, url, seendate, domain, sourcecountry) with
NO coordinates and NO event type. We therefore:
  1. Relevance-filter cheaply on title keywords BEFORE writing (heavy/Gemini triage is
     downstream in the Watcher — not here).
  2. Infer event_type and a coarse severity from title keywords.
  3. Dedupe on URL (the contract's GDELT dedupe key).
  4. Defer location to geocoding the headline (refine_place adopts the resolved
     formatted address as place_name); articles whose place can't be resolved are
     dropped rather than written with a misleading publisher-country location.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx

from common import make_event

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# The OR-query sent to GDELT — narrows the firehose to supply-chain-relevant disruption
# coverage at the source. Kept broad; the title keyword filter below is the real gate.
QUERY = (
    '("supply chain" OR "factory fire" OR "plant explosion" OR "chemical plant" OR '
    '"port strike" OR "port closure" OR "export ban" OR "product recall" OR '
    '"factory shutdown" OR "industrial accident") sourcelang:english'
)
TIMESPAN = "4h"
MAX_RECORDS = 75

# Title keyword → event_type. First match wins; ordering encodes precedence.
_TYPE_KEYWORDS = [
    ("explosion", "industrial_accident"),
    ("blast", "industrial_accident"),
    ("factory fire", "industrial_accident"),
    ("plant fire", "industrial_accident"),
    ("chemical", "industrial_accident"),
    ("industrial accident", "industrial_accident"),
    ("wildfire", "wildfire"),
    ("forest fire", "wildfire"),
    ("port strike", "port_disruption"),
    ("port closure", "port_disruption"),
    ("port", "port_disruption"),
    ("strike", "strike"),
    ("walkout", "strike"),
    ("recall", "recall"),
    ("flood", "flood"),
    ("hurricane", "hurricane"),
    ("cyclone", "hurricane"),
    ("typhoon", "hurricane"),
    ("earthquake", "earthquake"),
    ("drought", "drought"),
    ("frost", "frost"),
    ("export ban", "geopolitical"),
    ("sanction", "geopolitical"),
    ("tariff", "geopolitical"),
    ("blockade", "geopolitical"),
]

# Cheap relevance gate: a title must mention at least one of these to be written.
_RELEVANCE_TERMS = [kw for kw, _ in _TYPE_KEYWORDS] + [
    "supply chain",
    "shutdown",
    "shortage",
    "disruption",
    "evacuat",
]

# Coarse severity by inferred type (GDELT gives no magnitude).
_TYPE_SEVERITY = {
    "industrial_accident": 0.65,
    "wildfire": 0.6,
    "hurricane": 0.7,
    "earthquake": 0.6,
    "flood": 0.6,
    "port_disruption": 0.55,
    "strike": 0.5,
    "recall": 0.5,
    "drought": 0.5,
    "frost": 0.5,
    "geopolitical": 0.55,
    "other": 0.45,
}


async def fetch(client: httpx.AsyncClient) -> dict:
    resp = await client.get(
        DOC_API,
        params={
            "query": QUERY,
            "mode": "artlist",
            "format": "json",
            "maxrecords": MAX_RECORDS,
            "timespan": TIMESPAN,
            "sort": "datedesc",
        },
        timeout=25.0,
    )
    # GDELT throttles aggressively (~1 req / 5s). A rate-limited or briefly-unavailable
    # tick is a no-op, not a failure — the 5-min scheduler will catch up next cycle.
    if resp.status_code in (429, 503):
        return {"articles": []}
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        # GDELT returns an HTML/plain error page on a malformed query — treat as empty.
        return {"articles": []}


def _event_type(title_low: str) -> str:
    for kw, etype in _TYPE_KEYWORDS:
        if kw in title_low:
            return etype
    return "other"


def _is_relevant(title_low: str) -> bool:
    return any(term in title_low for term in _RELEVANCE_TERMS)


def _published_at(seendate: str | None) -> str | None:
    """GDELT seendate is 'YYYYMMDDTHHMMSSZ'."""
    if not seendate:
        return None
    try:
        dt = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def parse(raw: dict) -> list[dict]:
    events: list[dict] = []
    seen_urls: set[str] = set()
    for art in raw.get("articles", []):
        url = (art.get("url") or "").strip()
        title = (art.get("title") or "").strip()
        if not url or not title:
            continue
        if url in seen_urls:
            continue  # dedupe on URL at parse time too
        title_low = title.lower()
        if not _is_relevant(title_low):
            continue  # cheap relevance gate
        published_at = _published_at(art.get("seendate"))
        if published_at is None:
            continue

        seen_urls.add(url)
        etype = _event_type(title_low)
        country = art.get("sourcecountry") or "Global"
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

        events.append(
            make_event(
                id=f"gdelt-{digest}",
                source="gdelt",
                title=title,
                event_type=etype,
                place_name=country,        # coarse; refined from the geocoded headline
                geo_query=title,           # geocode the headline for the event location
                refine_place=True,
                severity_raw=_TYPE_SEVERITY.get(etype, 0.45),
                published_at=published_at,
                summary=f"{title} (via {art.get('domain', 'news')})",
                url=url,
            )
        )
    return events

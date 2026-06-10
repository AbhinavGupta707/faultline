"""GDACS global disasters — RSS/XML.

Feed: https://www.gdacs.org/xml/rss.xml  (RSS 2.0 with gdacs:/geo: namespaces).
Each <item> is a curated disaster with an alert level (Green/Orange/Red), an event
type code, a country, and a geo:Point.

XML is parsed with defusedxml when available (the deployed container installs it),
falling back to stdlib ElementTree locally — GDACS is a trusted source, but external
XML still warrants the hardened parser in production.
"""
from __future__ import annotations

from email.utils import parsedate_to_datetime

import httpx

try:  # hardened parser in the container; stdlib fallback for local/test
    from defusedxml.ElementTree import fromstring as _xml_fromstring
except ImportError:  # pragma: no cover - exercised only where defusedxml is absent
    from xml.etree.ElementTree import fromstring as _xml_fromstring

from common import make_event

FEED_URL = "https://www.gdacs.org/xml/rss.xml"

_NS = {
    "gdacs": "http://www.gdacs.org",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "georss": "http://www.georss.org/georss",
}

# GDACS eventtype code → our event_type enum.
_TYPE_MAP = {
    "EQ": "earthquake",
    "TC": "hurricane",
    "FL": "flood",
    "WF": "wildfire",
    "DR": "drought",
    "VO": "other",   # volcano — no enum member
    "TS": "other",   # tsunami — no enum member
}

# Alert level → severity_raw.
_ALERT_SEVERITY = {"Green": 0.3, "Orange": 0.6, "Red": 0.9}


async def fetch(client: httpx.AsyncClient) -> str:
    resp = await client.get(FEED_URL, timeout=25.0)
    resp.raise_for_status()
    return resp.text


def _text(item, path: str) -> str | None:
    el = item.find(path, _NS)
    return el.text.strip() if el is not None and el.text else None


def _coords(item) -> tuple[float, float] | None:
    lat = _text(item, "geo:lat") or _text(item, "geo:Point/geo:lat")
    lon = _text(item, "geo:long") or _text(item, "geo:Point/geo:long")
    if lat and lon:
        try:
            return float(lat), float(lon)
        except ValueError:
            pass
    pt = _text(item, "georss:point")
    if pt:
        parts = pt.split()
        if len(parts) == 2:
            try:
                return float(parts[0]), float(parts[1])
            except ValueError:
                pass
    return None


def _published_at(item) -> str | None:
    raw = _text(item, "pubDate")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return dt.isoformat().replace("+00:00", "Z")


def parse(raw: str) -> list[dict]:
    root = _xml_fromstring(raw)
    events: list[dict] = []
    for item in root.iter("item"):
        coords = _coords(item)
        if coords is None:
            continue  # GDACS always carries a point; skip the rare malformed item
        published_at = _published_at(item)
        if published_at is None:
            continue

        etype_code = (_text(item, "gdacs:eventtype") or "").upper()
        eventid = _text(item, "gdacs:eventid")
        if not eventid:
            continue
        alert = _text(item, "gdacs:alertlevel") or "Green"

        title = _text(item, "title") or "GDACS event"
        summary = _text(item, "description")
        country = _text(item, "gdacs:country")
        place_name = country or title

        events.append(
            make_event(
                id=f"gdacs-{etype_code or 'EV'}-{eventid}",
                source="gdacs",
                title=title,
                event_type=_TYPE_MAP.get(etype_code, "other"),
                lat=coords[0],
                lon=coords[1],
                place_name=place_name,
                severity_raw=_ALERT_SEVERITY.get(alert, 0.4),
                published_at=published_at,
                summary=summary,
                url=_text(item, "link"),
            )
        )
    return events

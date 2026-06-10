"""openFDA food enforcement (recalls) — JSON.

Feed: https://api.fda.gov/food/enforcement.json?search=report_date:[YYYYMMDD+TO+YYYYMMDD]
No API key needed at low volume. Records carry firm city/state/country text but no
coordinates, so they're emitted with a `_geo_query` and geocoded downstream.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from common import make_event

BASE_URL = "https://api.fda.gov/food/enforcement.json"
LOOKBACK_DAYS = 30
PAGE_LIMIT = 100

# FDA recall classification → severity. Class I is the most dangerous (reasonable
# probability of serious health consequences), Class III the least.
_CLASS_SEVERITY = {
    "Class I": 0.85,
    "Class II": 0.55,
    "Class III": 0.3,
}


async def fetch(client: httpx.AsyncClient) -> dict:
    today = datetime.now(tz=timezone.utc).date()
    start = today - timedelta(days=LOOKBACK_DAYS)
    # Spaces (not literal '+') so httpx encodes them as %20; a literal '+' becomes
    # %2B and openFDA 500s on the malformed range.
    search = f"report_date:[{start:%Y%m%d} TO {today:%Y%m%d}]"
    resp = await client.get(
        BASE_URL, params={"search": search, "limit": PAGE_LIMIT}, timeout=20.0
    )
    if resp.status_code == 404:
        # openFDA returns 404 with {"error":{"code":"NOT_FOUND"}} for an empty window.
        return {"results": []}
    resp.raise_for_status()
    return resp.json()


def _published_at(report_date: str | None) -> str | None:
    """openFDA dates are 'YYYYMMDD' → ISO date-time at UTC midnight."""
    if not report_date or len(report_date) != 8:
        return None
    try:
        d = datetime.strptime(report_date, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return d.isoformat().replace("+00:00", "Z")


def _place(rec: dict) -> str:
    parts = [rec.get("city"), rec.get("state"), rec.get("country")]
    return ", ".join(p for p in parts if p) or (rec.get("country") or "United States")


def parse(raw: dict) -> list[dict]:
    events: list[dict] = []
    for rec in raw.get("results", []):
        published_at = _published_at(rec.get("report_date"))
        if published_at is None:
            continue
        rid = rec.get("recall_number") or rec.get("event_id")
        if not rid:
            continue

        firm = rec.get("recalling_firm") or "Unknown firm"
        classification = rec.get("classification") or ""
        severity = _CLASS_SEVERITY.get(classification, 0.4)

        title = f"{classification} food recall — {firm}".strip(" —")
        reason = (rec.get("reason_for_recall") or "").strip()
        product = (rec.get("product_description") or "").strip()
        distribution = (rec.get("distribution_pattern") or "").strip()
        summary = " | ".join(
            s for s in (
                f"Reason: {reason}" if reason else "",
                f"Product: {product[:240]}" if product else "",
                f"Distribution: {distribution}" if distribution else "",
            ) if s
        )

        events.append(
            make_event(
                id=f"openfda-{rid}",
                source="openfda",
                title=title,
                event_type="recall",
                place_name=_place(rec),
                geo_query=_place(rec),
                severity_raw=severity,
                published_at=published_at,
                summary=summary or None,
            )
        )
    return events

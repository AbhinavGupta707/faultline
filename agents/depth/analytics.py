"""Analytics summary builder for GET /analytics/summary (Session G).

Thin query over the warehouse with a 60-second server-side cache (the cache lives in
api.py). Produces `$defs/analytics_summary`. If the warehouse is empty or unreachable it
self-falls-back to the bundled golden fixture so the endpoint is never a dead 500 — the
same forgiving contract the Analytics panel uses on the client side.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from .runstate import FIXTURES
from .warehouse import get_warehouse


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fixture_summary() -> dict[str, Any]:
    return json.loads((FIXTURES / "analytics_summary.json").read_text(encoding="utf-8"))


def summarize(window_days: int = 60, today: date | None = None, warehouse=None) -> dict[str, Any]:
    try:
        wh = warehouse or get_warehouse()
        body = wh.query_summary(window_days, today=today)
        if body.get("runs_count", 0) == 0:
            # nothing streamed/backfilled yet — serve the golden fixture
            fb = _fixture_summary()
            fb["generated_at"] = _now_iso()
            return fb
        body["generated_at"] = _now_iso()
        body["window_days"] = window_days
        return body
    except Exception:
        fb = _fixture_summary()
        fb["generated_at"] = _now_iso()
        return fb


if __name__ == "__main__":
    print(json.dumps(summarize(60, today=date(2026, 6, 10)), indent=2, default=str))

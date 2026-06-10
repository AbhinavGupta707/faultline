"""feed_ingest — normalizes live feeds (USGS/FDA/NOAA/GDACS/GDELT) → world-events docs.

Phase 0 stub — Session D implements per impl plan §10 (build order: USGS first).
Output spec: $defs/world_event in contracts/schemas/faultline.schema.json.
Writes to ELASTIC_EVENTS_INDEX (world-events-dev until sync S1).
"""
import os

from fastapi import FastAPI

app = FastAPI(title="feed-ingest")

SOURCES = ["usgs", "openfda", "noaa", "gdacs", "gdelt"]


@app.get("/health")
def health():
    return {"ok": True, "service": "feed-ingest",
            "mode": os.getenv("ELASTIC_MODE", "mock"),
            "version": "phase0-stub"}


@app.post("/ingest")
def ingest(source: str = "all"):
    if source != "all" and source not in SOURCES:
        return {"ok": False, "error": f"unknown source {source!r}"}
    return {"ok": True, "source": source, "written": 0, "skipped": 0}

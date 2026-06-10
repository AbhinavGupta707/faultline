"""feed_ingest — normalizes live feeds (USGS/FDA/NOAA/GDACS/GDELT) → world-events docs.

Cloud Run FastAPI service, Cloud Scheduler-triggered every 5 min. Each source is
normalized to `$defs/world_event` and bulk-written to ELASTIC_EVENTS_INDEX
(world-events-dev until sync S1; the semantic_text mapping populates `event_semantic`
server-side). Dedupe on id/url; severity_raw normalized to 0..1.

  POST /ingest?source=<usgs|noaa|gdacs|openfda|gdelt|all>  → {ok, source, written, skipped}
  GET  /health                                             → health_response
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI

from es_writer import write_events
from sources import ORDER, REGISTRY

app = FastAPI(title="feed-ingest")

# A descriptive UA is required by NOAA and good manners everywhere.
USER_AGENT = os.getenv(
    "FEED_USER_AGENT",
    "faultline-feed-ingest/1.0 (supply-chain control tower; contact ops@faultline.dev)",
)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "feed-ingest",
        "mode": os.getenv("ELASTIC_MODE", "mock"),
        "version": "0.1.0",
    }


async def _ingest_one(source: str, client: httpx.AsyncClient) -> dict:
    module = REGISTRY[source]
    raw = await module.fetch(client)
    docs = module.parse(raw)
    result = write_events(docs)
    return {"source": source, **result}


@app.post("/ingest")
async def ingest(source: str = "all"):
    if source != "all" and source not in REGISTRY:
        return {"ok": False, "error": f"unknown source {source!r}"}

    targets = ORDER if source == "all" else [source]
    written = skipped = 0
    per_source: dict[str, dict] = {}
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        for src in targets:
            try:
                res = await _ingest_one(src, client)
                written += res.get("written", 0)
                skipped += res.get("skipped", 0)
                per_source[src] = res
            except NotImplementedError:
                per_source[src] = {"source": src, "skipped_source": "not_implemented"}
            except Exception as exc:  # one bad feed must not sink the batch
                per_source[src] = {"source": src, "error": str(exc)}

    if source != "all":
        res = per_source.get(source, {})
        if "error" in res:
            return {"ok": False, "source": source, "error": res["error"]}
        return {"ok": True, "source": source,
                "written": res.get("written", 0), "skipped": res.get("skipped", 0)}

    return {"ok": True, "source": "all", "written": written, "skipped": skipped,
            "per_source": per_source}

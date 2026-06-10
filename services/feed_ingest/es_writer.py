"""Bulk writer for normalized world-events docs.

Idempotent: each doc is indexed under `_id = doc["id"]`, so re-ingesting the same
event overwrites rather than duplicating (the cross-batch dedupe). Within a single
batch we drop repeats sharing an `id` OR a non-empty `url` (the contract's
"dedupe on id/url"). The `elasticsearch` import is lazy so the test suite and the
no-credentials local path never need the client installed.

Until sync S1 this writes to `world-events-dev` (ELASTIC_EVENTS_INDEX); flipping that
env var to `world-events` is the only integration step.
"""
from __future__ import annotations

import os

DEFAULT_INDEX = "world-events-dev"


def events_index() -> str:
    return os.getenv("ELASTIC_EVENTS_INDEX", DEFAULT_INDEX)


def dedupe(docs: list[dict]) -> tuple[list[dict], int]:
    """Drop in-batch duplicates by id or url. Returns (unique_docs, skipped)."""
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    unique: list[dict] = []
    skipped = 0
    for d in docs:
        did = d.get("id")
        url = d.get("url") or None
        if did in seen_ids or (url is not None and url in seen_urls):
            skipped += 1
            continue
        if did:
            seen_ids.add(did)
        if url:
            seen_urls.add(url)
        unique.append(d)
    return unique, skipped


def _client():
    """Build an Elasticsearch client from env. Imported lazily on purpose."""
    from elasticsearch import Elasticsearch  # noqa: PLC0415 - lazy by design

    api_key = os.getenv("ELASTIC_API_KEY")
    # Agent Builder lives on Kibana; the ES data plane is the sibling es host.
    es_url = os.getenv("ELASTICSEARCH_URL") or os.getenv("ES_URL")
    if not es_url:
        raise RuntimeError(
            "ELASTICSEARCH_URL not set — cannot reach the cluster (live mode)."
        )
    return Elasticsearch(es_url, api_key=api_key) if api_key else Elasticsearch(es_url)


def write_events(docs: list[dict], *, index: str | None = None) -> dict:
    """Bulk-index deduped docs. Returns {written, skipped}.

    semantic_text (`event_semantic`) auto-populates on ingest — we never send it.
    """
    index = index or events_index()
    unique, skipped = dedupe(docs)
    if not unique:
        return {"written": 0, "skipped": skipped}

    if os.getenv("ELASTIC_MODE", "mock") != "live":
        # Mock / pre-S1: don't touch a cluster; report what *would* be written.
        return {"written": len(unique), "skipped": skipped, "dry_run": True}

    from elasticsearch.helpers import bulk  # noqa: PLC0415 - lazy by design

    es = _client()
    actions = [
        {"_op_type": "index", "_index": index, "_id": d["id"], "_source": d}
        for d in unique
    ]
    success, errors = bulk(es, actions, raise_on_error=False, stats_only=False)
    failed = len(errors) if isinstance(errors, list) else 0
    return {"written": success, "skipped": skipped + failed}

"""Idempotent Elastic setup — applies every index mapping in elastic/mappings/.

Connects with ELASTIC_ES_URL + ELASTIC_API_KEY (from repo-root .env), creates each
index if missing, and otherwise PUTs the mapping's `properties` to add any new fields
(idempotent: re-running is a no-op once everything exists). `semantic_text` fields carry
NO inference_id, so they use the Elastic-managed default ELSER endpoint — we never create
a custom inference id (impl plan §3.1).

Index name == mapping filename stem. semantic_text fields (suppliers.profile_semantic,
world-events.event_semantic) auto-run ELSER at ingest.

Run:
  python3 elastic/setup_elastic.py            # apply to the cluster
  python3 elastic/setup_elastic.py --dry-run  # validate JSON only, no cluster calls
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MAPPINGS = Path(__file__).parent / "mappings"
PIPELINES = Path(__file__).parent / "pipelines"


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    mapping_files = sorted(MAPPINGS.glob("*.json"))
    pipeline_files = sorted(PIPELINES.glob("*.json")) if PIPELINES.exists() else []

    # Validate every mapping + pipeline file parses before touching the cluster.
    parsed: list[tuple[str, dict]] = []
    for path in mapping_files:
        body = json.loads(path.read_text(encoding="utf-8"))
        parsed.append((path.stem, body))
    pipelines = [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in pipeline_files]

    if dry_run:
        for name, _ in pipelines:
            print(f"would apply pipeline: {name}")
        for name, _ in parsed:
            print(f"would apply mapping: {name}")
        print(f"--dry-run — {len(pipelines)} pipelines + {len(parsed)} mappings validated; "
              "no cluster calls made.")
        return 0

    from _env import Elastic  # local import so --dry-run needs no creds/requests

    es = Elastic()

    # Pipelines first — indices may reference them as default_pipeline (PUT is idempotent).
    for name, body in pipelines:
        r = es.es("PUT", f"/_ingest/pipeline/{name}", json=body)
        if r.status_code not in (200, 201):
            print(f"ERROR creating pipeline {name}: {r.status_code} {r.text[:300]}")
            return 1
        print(f"pipeline ok: {name}")

    created, updated, unchanged = [], [], []

    for name, body in parsed:
        exists = es.es("HEAD", f"/{name}").status_code == 200
        if not exists:
            r = es.es("PUT", f"/{name}", json=body)
            if r.status_code in (200, 201):
                created.append(name)
            elif "resource_already_exists_exception" in r.text:
                exists = True  # raced; fall through to mapping update
            else:
                print(f"ERROR creating {name}: {r.status_code} {r.text[:300]}")
                return 1
        if exists:
            props = body.get("mappings", {}).get("properties")
            if not props:
                unchanged.append(name)
                continue
            r = es.es("PUT", f"/{name}/_mapping", json={"properties": props})
            if r.status_code == 200:
                updated.append(name)
            else:
                # adding fields can fail if a type changed — surface it, don't hide it
                print(f"WARN updating mapping {name}: {r.status_code} {r.text[:300]}")
                unchanged.append(name)

    print(f"created:   {created}")
    print(f"updated:   {updated}")
    print(f"unchanged: {unchanged}")
    print(f"setup_elastic OK — {len(parsed)} indices ensured on the cluster.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

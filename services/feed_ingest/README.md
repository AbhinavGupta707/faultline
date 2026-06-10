# feed_ingest

Cloud Run FastAPI service (Session D). Normalizes five live, free, real-time feeds into
`world-events` docs and bulk-writes them to Elasticsearch. Cloud Scheduler hits
`POST /ingest?source=all` every 5 minutes. The `semantic_text` mapping populates
`event_semantic` server-side on ingest — this service never sends it.

Output spec: `$defs/world_event` in `contracts/schemas/faultline.schema.json` (FROZEN).

## Endpoints
- `POST /ingest?source=<usgs|noaa|gdacs|openfda|gdelt|all>` → `{ok, source, written, skipped}`
  (the `all` form also returns `per_source` diagnostics). One bad feed never sinks the batch.
- `GET /health` → `health_response` (`service: "feed-ingest"`).

## Feeds (build order = value order)
| # | source | format | geo | severity_raw basis |
|---|---|---|---|---|
| 1 | USGS all_hour | GeoJSON | point | magnitude / 10 |
| 2 | openFDA food enforcement | JSON | geocoded firm city/state | recall class (I .85 / II .55 / III .3) |
| 3 | NOAA/NWS active alerts | GeoJSON | polygon centroid or geocoded area | NWS severity (Extreme .95 … Minor .3); kept ≥ Moderate, Actual only |
| 4 | GDACS | RSS/XML | geo:Point / georss | alert level (Red .9 / Orange .6 / Green .3) |
| 5 | GDELT 2.0 Doc | JSON | geocoded headline | coarse, by inferred type |

GDELT is relevance-filtered with cheap title-keyword heuristics **before** writing
(Gemini triage is downstream in the Watcher, not here) and deduped on URL. GDELT
throttles aggressively (~1 req/5s); a `429/503` tick is treated as an empty no-op.

`region` is a coarse lat/lon bucket (`common.region_for`); vocabulary matches the golden
fixtures (`south-asia`, `southeast-asia`, `north-america`, `latam`, …).

## Geocoding
openFDA and GDELT carry place text, not coordinates. They emit a deferred doc; the
ingest pipeline geocodes via the Maps Geocoding REST API (`geocode.resolve_locations`),
adopting the formatted address as `place_name` for GDELT. **Unresolvable locations are
dropped, never written with a misleading location** — counted in `skipped`.

## Dedupe
In-batch dedupe on `id` or non-empty `url`; cross-batch idempotency via `_id = doc.id`
(re-ingest overwrites, never duplicates).

## Config
| env | meaning |
|---|---|
| `ELASTIC_MODE` | `mock` (default, dry-run — no cluster touched) \| `live` |
| `ELASTIC_EVENTS_INDEX` | target index — `world-events-dev` until sync **S1**, then `world-events` |
| `ELASTICSEARCH_URL` | **ES data-plane** URL (NOT `KIBANA_URL`) — required in live mode. *Session F: add to env.example at S1.* |
| `ELASTIC_API_KEY` | cluster API key |
| `MAPS_API_KEY` | Maps Geocoding (without it, geo-less feed items are dropped) |
| `FEED_USER_AGENT` | UA sent to all feeds (NOAA requires a descriptive one) |

## Tests
Offline, no network/ES: `python3 -m pytest tests/` — one suite per feed against a
captured sample payload, validating normalized docs against the frozen `world_event`
schema.

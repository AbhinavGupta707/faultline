# STATUS — per-branch heartbeat (append one line per milestone; owned per-branch, never merged across)

2026-06-10 · P0 · Phase 0 bootstrap in progress.
2026-06-10 · D · feed_ingest scaffold + USGS end-to-end: live all_hour.geojson → world_event docs, region/severity normalize, id/url dedupe, ES bulk writer (lazy, dry-run pre-S1), Maps geocode helper. USGS unit tests green (6/6), live ingest verified (6 quakes). Writes world-events-dev until S1.
2026-06-10 · D · openFDA food enforcement (feed 2/5): recall class→severity, deferred geocoding pipeline (resolve_locations drops unresolvable, never half-writes). Live fetch verified (100 recalls). Tests 12/12.
2026-06-10 · D · NOAA/NWS active alerts (feed 3/5): UA header, polygon centroid or null-geom geocode, event-text→type map, Actual+Moderate filter. Live verified (321→231 kept). Tests 17/17.
2026-06-10 · D · GDACS RSS/XML (feed 4/5): defusedxml (stdlib fallback), eventtype/alertlevel maps, geo:Point + georss fallback, RFC822 pubDate. Live verified (98 events). Tests 23/23.
2026-06-10 · D · GDELT 2.0 Doc API (feed 5/5): supply-chain OR-query, cheap title relevance gate, type inference, URL dedupe, headline-geocode w/ place refine. 429/503 → no-op tick. Parse verified vs sample (live throttled — respected by 5-min cadence). ALL 5 FEEDS DONE. Tests 29/29.

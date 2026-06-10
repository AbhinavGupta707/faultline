# Contract — HTTP API surface

> **FROZEN at `phase0`.** Only Session F amends. Canonical schemas:
> [`schemas/faultline.schema.json`](schemas/faultline.schema.json). All bodies JSON
> unless noted. Errors: appropriate 4xx/5xx with `{ "error": "<message>" }`.

## Agent runtime (Cloud Run, FastAPI — Session B owns the implementation)

### `GET /health`
→ 200 `$defs/health_response`: `{ ok, service: "faultline-agent", mode?: "mock"|"live", elastic_ok?, version? }`
(Every service in the repo exposes the same shape with its own `service` name.)

### `GET /ws`
WebSocket upgrade — protocol in [`ws_protocol.md`](ws_protocol.md).

### `POST /whatif`
Body `$defs/whatif_request`: `{ scenario: whatif_scenario }` —
`{ event_type, location {lat,lon}, duration_days, magnitude(0–1), title?, place_name?, preset? }`.
Server writes a synthetic `world-events` doc (`simulated:true`, `source:"whatif"`) and starts
the identical pipeline.
→ 202 `$defs/whatif_response`: `{ accepted: true, run_id, event_id }`
Golden examples: [`fixtures/whatif_scenario.json`](fixtures/whatif_scenario.json) (request) ·
preset keys shipped at Phase 0: `minas-frost` ("Frost in Minas Gerais"), `suez-closure-3w`
("Suez closes 3 weeks"), `gulf-hurricane` ("Hurricane hits US Gulf Coast petrochem"),
`busan-port-strike` ("Port of Busan strike, 10 days").

### `POST /approval`
Body `$defs/approval_post_request`: `{ approval_id, approved, note? }` (same semantics as
ws `approval.decision`; idempotent per `approval_id`).
→ 200 `$defs/approval_post_response`: `{ ok, approval_id, applied }`

### `GET /report/{run_id}`
The Briefer's situation report for a run (Session G registers the implementation;
the route lives on the agent runtime).
- default → 200 `application/pdf` (or 302 to a signed GCS URL — both legal)
- `?format=md` → 200 `text/markdown`
- 404 `{ "error": "report not ready" }` until the Briefer has emitted `kind:"brief"`.

### `GET /analytics/summary`
→ 200 `$defs/analytics_summary` (Session G; thin BigQuery query, 60 s server-side cache):
`{ generated_at, window_days, runs_count, dollars_at_risk_avoided_usd, includes_backfill?,
risk_over_time: [{date, product_id, product_name?, severity_avg, dollars_at_risk_usd}],
top_chokepoints: [{supplier_id, name, country, tier?, incident_count, products_affected[]}] }`
Golden example: [`fixtures/analytics_summary.json`](fixtures/analytics_summary.json)

## po_generator (Cloud Run — Session D)

### `POST /po/render`
Body `$defs/draft_po_payload` → renders the branded contingent-PO PDF to GCS.
→ 200 `{ ok: true, po_id, pdf_gcs_uri }`
Golden input: [`fixtures/draft_po.json`](fixtures/draft_po.json)

### `GET /health` → `health_response` (`service: "po-generator"`)

## feed_ingest (Cloud Run — Session D)

### `POST /ingest?source=<usgs|noaa|gdacs|openfda|gdelt|all>`
Cloud Scheduler target (every 5 min). Normalizes feeds → bulk-writes `$defs/world_event`
docs to `ELASTIC_EVENTS_INDEX` (dedupe on `id`/`url`).
→ 200 `{ ok: true, source, written: <int>, skipped: <int> }`

### `GET /health` → `health_response` (`service: "feed-ingest"`)

## voice_gateway (Cloud Run — Session E)

### `GET /health` → `health_response` (`service: "voice-gateway"`)

### `WS /voice/intent` — push-to-talk voice-in
1. client → JSON `$defs/voice_in_client_msg` `{ type:"start", sample_rate_hz:16000, encoding:"pcm16" }`
2. client → **binary** frames: raw little-endian 16-bit PCM, 16 kHz mono, ≤8 KB per frame
3. client → JSON `{ type:"stop" }`
4. server → JSON `$defs/voice_in_server_msg`: `transcript.partial` / `transcript.final`
   (`{text}`), then `{ type:"intent", transcript, intent: $defs/voice_intent }`.
   Optional spoken ack: `{ type:"audio.start", sample_rate_hz:24000 }` followed by binary
   PCM16 24 kHz frames.
The **frontend** (features/voice) forwards the intent to the agent runtime as a ws
`voice.intent` message — the gateway never talks to the agent directly.

### `WS /voice/call` — in-app negotiation call (voice-out)
1. client → JSON `$defs/voice_call_client_msg` `{ type:"call.start", call_id, po_id }`
2. server → JSON `$defs/voice_call_server_msg` `{ type:"call.event", payload: $defs/call_event_payload }`
   for every status/transcript/summary beat (same payloads the agent runtime mirrors as
   `agent.emit kind:"call_event"`), interleaved with `{ type:"audio.start", sample_rate_hz:24000 }`
   + binary PCM16 frames for the audible call audio.
3. client → `{ type:"call.end", call_id }` to hang up.
Golden transcript: [`fixtures/call_transcript.json`](fixtures/call_transcript.json)

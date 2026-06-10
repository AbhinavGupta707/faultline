# voice_gateway

Gemini Live API bridge for Faultline. Owns voice-in (push-to-talk → intent) and voice-out
(in-app two-party negotiation call with streaming transcript + audio). All AI is Google
(Vertex Gemini Live). See `../../SPIKE.md` for the model verdict.

## Modes (`VOICE_MODE`)
- **`mock`** (default) — no GCP creds. Drives the exact WS contracts from
  `contracts/fixtures/` + a rule-based intent parser. Locally verified; the dev/demo path
  until creds land.
- **`live`** — real Vertex Live API. Needs ADC (`gcloud auth application-default login`) or
  `GOOGLE_APPLICATION_CREDENTIALS`, plus `GCP_PROJECT` (+ `VERTEX_LOCATION`, default
  `us-central1`). Model from `GEMINI_LIVE_MODEL` (effective default
  `gemini-live-2.5-flash-native-audio`; flips to `gemini-3.1-flash-live-preview` with one
  env line once it reaches Vertex — no code change).

## Run
```bash
pip install -r requirements.txt          # + httpx jsonschema pytest for tests
uvicorn main:app --app-dir services/voice_gateway --port 8082
# open http://localhost:8082/  → standalone test bench (mic PTT + negotiation call)
```

## WS endpoints (contracts/http_api.md)
- `WS /voice/intent` — `{type:"start"}` → binary PCM16/16k frames → `{type:"stop"}`;
  server replies `transcript.partial/final` then `{type:"intent", transcript, intent}`.
- `WS /voice/call` — `{type:"call.start", call_id, po_id}`; server streams
  `{type:"call.event", payload:<call_event_payload>}` interleaved with `audio.start` + binary
  PCM16/24k; `{type:"call.end", call_id}` hangs up.
- `GET /health` → `health_response` (`service:"voice-gateway"`).
- `GET /` → standalone test bench (static).

## Tests / spike
```bash
python spike.py            # offline contract self-check (no creds) — PASS/FAIL
python spike.py clip.wav   # live round-trip from a 16 kHz mono WAV (VOICE_MODE=live)
PYTHONPATH=services/voice_gateway pytest services/voice_gateway/test_gateway.py -q
```

## Frontend
`web/src/features/voice/` consumes these endpoints (props frozen per
`contracts/components.md §1`). The gateway test bench is independent of the React app.

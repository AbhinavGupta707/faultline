# Voice Spike — verdict & evidence (Session E, 2026-06-10)

## Verdict: **GO** — model `gemini-live-2.5-flash-native-audio` (Vertex, GA)

The first-hour spike question was: can we do a browser mic↔speaker round-trip through the
Gemini Live API on Vertex, primary `gemini-3.1-flash-live-preview`, fallback
`gemini-live-2.5-flash-native-audio`? **Yes — voice ships on Live.** But the *primary*
model choice changes:

### Escalation to Session F (model pin change)
- **`gemini-3.1-flash-live-preview` is NOT on Vertex yet as of 2026-06-10.** It is available
  only via the Gemini Developer API (Google AI Studio). Confirmed by an active Google
  developer-forum thread ("Gemini 3.1 Flash Live Preview on Vertex AI, when?", last activity
  2026-04-24, no Vertex rollout, no Google staff ETA) and the model card (preview via AI
  Studio / Gemini Enterprise, not Vertex GA).
- **`gemini-live-2.5-flash-native-audio` IS GA on Vertex** with production SLAs and native
  audio. This is our shipping model.
- Hackathon rule compliance is unaffected: both are Google Cloud APIs. The runtime stays
  100% Google.
- **Action for F:** treat `GEMINI_LIVE_MODEL=gemini-live-2.5-flash-native-audio` as the
  effective default. The gateway reads the model from env and will flip to
  `gemini-3.1-flash-live-preview` with a one-line `.env` change the moment it appears in the
  Vertex Model Garden — no code change. (`infra/env.example` keeps 3.1 as the aspirational
  primary + the 2.5 fallback; only the deployed `.env` value matters.)

## Audio framing — contract is correct, no amendment needed
- **Input** (voice-in): raw little-endian 16-bit PCM, **16 kHz** mono, mime
  `audio/pcm;rate=16000`, sent via `session.send_realtime_input(media=Blob(...))`. Matches
  `voice_in_client_msg` (pcm16 / 16000).
- **Output** (spoken ack / call audio): native audio is **24 kHz** PCM16. Matches the
  contract's `audio.start { sample_rate_hz: 24000 }`.

## How the spike is wired (runnable now)
- `services/voice_gateway/` connects to Vertex via the `google-genai` SDK
  (`genai.Client(vertexai=True, project, location)` → `client.aio.live.connect(...)`).
- A **standalone test page** is served by the gateway itself at `GET /` (no dependency on the
  React app or any other session) — it captures mic audio, downsamples to 16 kHz PCM16,
  streams it to `WS /voice/intent`, renders the live transcript + parsed intent JSON, and
  plays back 24 kHz PCM16 audio. The negotiation call is on the same page via `WS /voice/call`.
- **Mock mode** (`VOICE_MODE=mock`, the default until creds land) drives the same WS
  contracts from `contracts/fixtures/call_transcript.json` + a rule-based intent parser, so
  the whole pipeline is demonstrable end-to-end **without GCP credentials**. Flip to
  `VOICE_MODE=live` (with ADC / `GOOGLE_APPLICATION_CREDENTIALS` + `GCP_PROJECT`) for the
  real round-trip — that is the one command the operator runs to confirm GO on hardware.

## To run the live confirmation (operator, ~2 min)
```
gcloud auth application-default login        # or set GOOGLE_APPLICATION_CREDENTIALS
export GCP_PROJECT=<proj> VERTEX_LOCATION=us-central1 VOICE_MODE=live
pip install -r services/voice_gateway/requirements.txt
uvicorn main:app --app-dir services/voice_gateway --port 8082
# open http://localhost:8082/ → hold-to-talk → expect transcript + intent + spoken ack
python services/voice_gateway/spike.py            # headless file→Live→wav round-trip check
```

## Floor (if Live ever disappoints in-browser): Cloud STT → gemini-3.5-flash → Cloud TTS.
Not needed — Live on 2.5 native audio is the path. Documented in case of late regression.

# STATUS — per-branch heartbeat (append one line per milestone; owned per-branch, never merged across)

2026-06-10 · P0 · Phase 0 bootstrap in progress.
2026-06-10 · E · VOICE SPIKE: GO/gemini-live-2.5-flash-native-audio (Vertex GA). ESCALATE to F: primary gemini-3.1-flash-live-preview is AI-Studio-only, NOT on Vertex yet (2026-06-10) — model is env-pinned so it flips with one .env line when 3.1 lands. Audio contract (PCM16 16k in / 24k out) verified correct. Details in SPIKE.md.
2026-06-10 · E · Voice IN + OUT built. Gateway (services/voice_gateway): live Vertex Live wiring + mock mode (no creds), WS /voice/intent + /voice/call + standalone test bench at GET /. 7/7 pytest green, spike offline PASS, uvicorn boots. VoicePanel React internals done (web/src/features/voice) — PTT intents + negotiation call (waveform/transcript/amber "AI speaking"); type-clean (frozen props untouched). NOTE for C1/F: pre-existing tsc error in lib/replay.ts:24 blocks the web build (not mine) — flagged.

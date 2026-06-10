"""Mock mode — drives the identical WS contracts with zero GCP credentials.

This is the locally-verified path (the dev sandbox has no gcloud/ADC). It lets the standalone
test page and the React VoicePanel be developed and demoed end-to-end, and lets the contract
be tested in CI. Flip to live mode with ``VOICE_MODE=live`` + creds.

Voice-in: rule-based intent over a transcript (real mic audio is ignored in mock; the client
may pass an optional ``text`` hint, else a default demo command is used).
Voice-out: replays the golden negotiation transcript with realistic pacing, plus a synthesized
placeholder tone per line so the 24 kHz audio path (waveform / "AI speaking" indicator) is
exercised without TTS.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import struct
from typing import AsyncIterator

from config import CONFIG
from intent import rule_based_intent

# Default demo utterance if the client supplies no transcript hint in mock mode.
DEFAULT_DEMO_UTTERANCE = "what's my biggest risk right now?"

# Embedded copy of contracts/fixtures/call_transcript.json so mock mode works inside the
# container (which copies only the service dir). The on-disk fixture is preferred when present.
_EMBEDDED_CALL = [
    {"call_id": "call-20260610-01", "event": "status", "status": "initiating"},
    {"call_id": "call-20260610-01", "event": "status", "status": "connected"},
    {"call_id": "call-20260610-01", "event": "transcript", "speaker": "faultline_agent",
     "text": "Good afternoon — this is Faultline, the AI procurement agent calling on behalf of "
             "Northwind Provisions about emulsifier supply. Our Gujarat source is offline due to "
             "flooding, and we'd like to confirm the availability you quoted.", "is_final": True},
    {"call_id": "call-20260610-01", "event": "transcript", "speaker": "supplier",
     "text": "Hello Faultline, this is Jurong Fine Ingredients order desk. Yes — we hold finished "
             "E471/E414 beverage blend in Singapore. Twelve thousand kilograms is available, and we "
             "can split air and sea as quoted.", "is_final": True},
    {"call_id": "call-20260610-01", "event": "transcript", "speaker": "faultline_agent",
     "text": "We need three thousand kilograms delivered to Navi Mumbai within seven days, with the "
             "nine-tonne balance to Rotterdam by sea. Can you commit to air dispatch this week at the "
             "quoted four dollars eighty-five per kilogram?", "is_final": True},
    {"call_id": "call-20260610-01", "event": "transcript", "speaker": "supplier",
     "text": "Confirmed. Three thousand kilograms by air arriving June seventeenth, nine thousand by "
             "sea arriving June twenty-sixth, and we will hold four eighty-five per kilogram for this "
             "order.", "is_final": True},
    {"call_id": "call-20260610-01", "event": "summary",
     "summary": {"agreed": True, "lead_time_days": 7, "expedited_lead_time_days": 7,
                 "quantity": 12000, "unit_price_usd": 4.85,
                 "notes": "3,000 kg air → Navi Mumbai 2026-06-17; 9,000 kg sea → Rotterdam 2026-06-26. "
                          "Price held. Agent self-identified as AI; commitment contingent on PO approval "
                          "(po-2026-0042)."}},
    {"call_id": "call-20260610-01", "event": "status", "status": "ended"},
]


def load_call_transcript() -> list[dict]:
    """Prefer the on-disk golden fixture (dev); fall back to the embedded copy (container)."""
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(6):
        candidate = os.path.join(cur, "contracts", "fixtures", "call_transcript.json")
        if os.path.exists(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, json.JSONDecodeError):
                break
        cur = os.path.dirname(cur)
    return _EMBEDDED_CALL


def mock_intent(transcript: str | None, pending_approval_id: str | None) -> tuple[str, dict]:
    text = (transcript or "").strip() or DEFAULT_DEMO_UTTERANCE
    return text, rule_based_intent(text, pending_approval_id)


def tone(seconds: float, freq: float = 180.0, rate: int | None = None, volume: float = 0.18) -> bytes:
    """Synthesize a soft PCM16 sine tone (placeholder 'voice' so the audio path animates)."""
    rate = rate or CONFIG.output_sample_rate_hz
    n = int(seconds * rate)
    out = bytearray()
    for i in range(n):
        # gentle fade in/out to avoid clicks
        env = min(1.0, i / (rate * 0.02), (n - i) / (rate * 0.02))
        sample = int(volume * env * 32767 * math.sin(2 * math.pi * freq * i / rate))
        out += struct.pack("<h", max(-32768, min(32767, sample)))
    return bytes(out)


async def stream_mock_call(call_id: str, pace: float = 1.0) -> AsyncIterator[dict]:
    """Yield wire-ready dicts: {'json': <call_event_payload-or-control>} and, for spoken lines,
    a preceding {'audio_start': rate} then {'audio': pcm_bytes}. The route serializes these.
    """
    events = load_call_transcript()
    for ev in events:
        ev = dict(ev)
        ev["call_id"] = call_id
        kind = ev.get("event")
        if kind == "status":
            yield {"json": ev}
            await asyncio.sleep(0.4 * pace)
        elif kind == "transcript":
            # placeholder audio: ~1s per spoken line, two pitches by speaker
            freq = 200.0 if ev.get("speaker") == "faultline_agent" else 150.0
            yield {"audio_start": CONFIG.output_sample_rate_hz}
            yield {"audio": tone(1.1, freq=freq)}
            yield {"json": ev}
            await asyncio.sleep(1.4 * pace)
        elif kind == "summary":
            yield {"json": ev}
            await asyncio.sleep(0.3 * pace)
        else:
            yield {"json": ev}

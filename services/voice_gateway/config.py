"""Runtime configuration for the voice gateway.

Two modes, selected by ``VOICE_MODE``:

* ``live``  — real Gemini Live API on Vertex (needs ADC / GOOGLE_APPLICATION_CREDENTIALS
              + GCP_PROJECT). This is the demo/production path.
* ``mock``  — no cloud creds required; drives the identical WS contracts from
              ``contracts/fixtures/`` + a rule-based intent parser. Default until creds
              land, so the whole pipeline is demonstrable end-to-end on a laptop.

Model pin: spike verdict (SPIKE.md) is that ``gemini-3.1-flash-live-preview`` is not on
Vertex yet (2026-06-10); the shipping model is ``gemini-live-2.5-flash-native-audio``.
The model is read from env so it flips with one ``.env`` line — never hard-coded.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _clean(val: str | None) -> str | None:
    if val is None:
        return None
    val = val.strip()
    return val or None


@dataclass(frozen=True)
class Config:
    # mock until the operator sets VOICE_MODE=live with real creds.
    mode: str = field(default_factory=lambda: (_clean(os.getenv("VOICE_MODE")) or "mock").lower())

    # Vertex
    project: str | None = field(default_factory=lambda: _clean(os.getenv("GCP_PROJECT")))
    location: str = field(default_factory=lambda: _clean(os.getenv("VERTEX_LOCATION")) or "us-central1")

    # Models. live_model is the effective Live model; we keep the fallback explicit so a
    # transient "model not found" on the primary auto-degrades instead of failing the demo.
    live_model: str = field(
        default_factory=lambda: _clean(os.getenv("GEMINI_LIVE_MODEL"))
        or "gemini-live-2.5-flash-native-audio"
    )
    live_model_fallback: str = field(
        default_factory=lambda: _clean(os.getenv("GEMINI_LIVE_MODEL_FALLBACK"))
        or "gemini-live-2.5-flash-native-audio"
    )
    flash_model: str = field(
        default_factory=lambda: _clean(os.getenv("GEMINI_MODEL_FLASH")) or "gemini-2.5-flash"
    )
    # Text model used to parse the voice transcript into an intent. Defaults to an
    # actually-available model: the live probe found gemini-3.5-flash 404s on the hack
    # project; only the 2.5 family is present. Intent parsing is OPTIONAL — rule_based_intent
    # is the always-on fallback, so a 404 here never breaks voice-in.
    intent_model: str = field(
        default_factory=lambda: _clean(os.getenv("GEMINI_INTENT_MODEL")) or "gemini-2.5-flash"
    )
    # Set GEMINI_INTENT_USE_LLM=0 to skip the LLM and always use the rule-based parser.
    intent_use_llm: bool = field(
        default_factory=lambda: (_clean(os.getenv("GEMINI_INTENT_USE_LLM")) or "1") not in ("0", "false", "no")
    )

    # Audio framing — fixed by the frozen contract (http_api.md / voice_in_client_msg).
    input_sample_rate_hz: int = 16000   # mic → gateway (PCM16 LE mono)
    output_sample_rate_hz: int = 24000  # gateway → speaker (native-audio PCM16)

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def live_ready(self) -> bool:
        """True when a live session could plausibly be opened (creds + project present)."""
        if not self.is_live:
            return False
        if not self.project:
            return False
        has_adc = bool(
            _clean(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
            or os.path.exists(
                os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
            )
        )
        return has_adc


CONFIG = Config()


def describe() -> dict:
    """Compact, secret-free snapshot for /health."""
    return {
        "mode": CONFIG.mode,
        "live_model": CONFIG.live_model,
        "location": CONFIG.location,
        "project_set": bool(CONFIG.project),
        "live_ready": CONFIG.live_ready,
    }

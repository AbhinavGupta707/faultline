"""Gemini Live API (Vertex) wrappers.

`google-genai` is imported lazily so the module loads — and mock mode runs — without the
package or any GCP credentials installed. Live mode is the deployed path; per the spike
(SPIKE.md) it runs on ``gemini-live-2.5-flash-native-audio`` until 3.1-flash-live reaches
Vertex, selected via ``GEMINI_LIVE_MODEL``.

Audio framing (frozen contract): input PCM16 mono 16 kHz; output native audio PCM16 24 kHz.

NOTE: exact `google-genai` Live symbols shift between minor versions. We use dict-based
configs + `types.Blob` (the stable surface) and degrade gracefully; verify against the
installed SDK version at deploy time. The mock path is the locally-verified one.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator, Awaitable, Callable

from config import CONFIG
from personas import (
    CallContext,
    negotiator_system_prompt,
    supplier_system_prompt,
)

log = logging.getLogger("voice_gateway.live")

_INPUT_MIME = f"audio/pcm;rate={CONFIG.input_sample_rate_hz}"


def _client():
    """Vertex genai client. Lazy import — only reached in live mode."""
    from google import genai  # noqa: WPS433 (deliberate lazy import)

    return genai.Client(
        vertexai=True,
        project=CONFIG.project,
        location=CONFIG.location,
    )


_RESOLVED_MODEL: str | None = None


async def resolve_model(client) -> str:
    """Return the first Live model that actually connects on this Vertex project.

    Tries ``GEMINI_LIVE_MODEL`` then ``GEMINI_LIVE_MODEL_FALLBACK``. Per the spike,
    gemini-3.1-flash-live-preview is not on Vertex yet (2026-06-10), so this transparently
    degrades to gemini-live-2.5-flash-native-audio. Result is cached for the process.
    """
    global _RESOLVED_MODEL
    if _RESOLVED_MODEL:
        return _RESOLVED_MODEL

    candidates = [CONFIG.live_model]
    if CONFIG.live_model_fallback and CONFIG.live_model_fallback not in candidates:
        candidates.append(CONFIG.live_model_fallback)

    last_err: Exception | None = None
    for model in candidates:
        try:
            # Probe with AUDIO — the native-audio model rejects TEXT output (1007).
            async with client.aio.live.connect(model=model, config={"response_modalities": ["AUDIO"]}):
                pass
            _RESOLVED_MODEL = model
            log.info("live model resolved: %s", model)
            return model
        except Exception as exc:  # noqa: BLE001 — probe; try the next candidate
            last_err = exc
            log.warning("live model %s unavailable (%s); trying next", model, exc)
    raise RuntimeError(f"no Live model available on Vertex: {last_err}")


def _send_audio(session, chunk: bytes):
    """Forward a PCM16/16k frame to the Live session, tolerant of SDK kwarg drift."""
    from google.genai import types

    blob = types.Blob(data=chunk, mime_type=_INPUT_MIME)
    try:
        return session.send_realtime_input(audio=blob)
    except TypeError:
        return session.send_realtime_input(media=blob)


# ──────────────────────────────────────────────────────────────────────────────
# Voice IN.  The Live native-audio model is built for full-duplex *conversation* and does
# NOT emit input transcription for one-shot buffered push-to-talk audio (verified: zero
# messages back). So voice-in transcribes + parses intent in a single multimodal call to
# gemini-2.5-flash with the mic audio as an inline WAV Part (verified accurate, all-Google).
# rule_based_intent is the always-on fallback so a model error never breaks voice-in.
# ──────────────────────────────────────────────────────────────────────────────
async def transcribe_and_parse(
    audio_chunks: AsyncIterator[bytes],
    pending_approval_id: str | None,
    on_partial: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str, dict]:
    """Buffer push-to-talk audio → one gemini-2.5-flash call → (transcript, voice_intent)."""
    from intent import coerce_intent, rule_based_intent

    pcm = bytearray()
    async for chunk in audio_chunks:
        if chunk:
            pcm.extend(chunk)
    if not pcm or not CONFIG.intent_use_llm:
        return "", rule_based_intent("", pending_approval_id)

    wav = _pcm16_to_wav(bytes(pcm), CONFIG.input_sample_rate_hz)
    client = _client()
    try:
        from google.genai import types

        system = _audio_intent_prompt(pending_approval_id)
        resp = await client.aio.models.generate_content(
            model=CONFIG.intent_model,
            contents=[types.Part.from_bytes(data=wav, mime_type="audio/wav"), "Parse the spoken command."],
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        import json as _json

        obj = _json.loads(resp.text or "{}")
        transcript = str(obj.get("transcript") or obj.get("text") or "").strip()
        intent = coerce_intent(obj, transcript, pending_approval_id)
        if on_partial and transcript:
            await on_partial(transcript)
        return transcript, intent
    except Exception as exc:  # noqa: BLE001 — degrade, keep voice-in alive
        log.warning("voice-in audio intent (%s) failed: %s; rule-based fallback", CONFIG.intent_model, exc)
        return "", rule_based_intent("", pending_approval_id)


def _audio_intent_prompt(pending_approval_id: str | None) -> str:
    base = (
        "You are the voice command parser for Faultline, a supply-chain control tower. "
        "Listen to the audio and output ONLY one minified JSON object, no prose, no code fence:\n"
        '{"transcript": <verbatim words>, '
        '"action": one of "query"|"approve"|"reject"|"show"|"whatif"|"unknown", '
        '"confidence": <0..1>, "product_id": <optional>, "supplier_id": <optional>, '
        '"text": <normalized command>}\n'
        "Rules: approve/reject when the user decides a pending approval (e.g. 'approve the "
        "re-source for the cold-brew line'); show when focusing the map on something; query for "
        "questions about state; whatif for hypotheticals ('what if Busan port closes'); unknown "
        "if unclear (low confidence)."
    )
    if pending_approval_id:
        base += f'\nA pending approval exists: set "approval_id":"{pending_approval_id}" for approve/reject.'
    return base


def _pcm16_to_wav(pcm: bytes, rate: int) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Voice OUT — two-party negotiation call. Two Live AUDIO sessions (negotiator + supplier);
# each persona's turn is driven by the other party's transcribed line, giving deterministic
# turn-taking with natural native-audio voice. Yields (speaker, text, audio_bytes) per turn.
# ──────────────────────────────────────────────────────────────────────────────
async def run_negotiation_call(
    ctx: CallContext,
    max_turns: int | None = None,
) -> AsyncIterator[tuple[str, str, bytes]]:
    if max_turns is None:
        max_turns = int(os.getenv("VOICE_CALL_MAX_TURNS", "6"))
    client = _client()

    neg_cfg = {
        "response_modalities": ["AUDIO"],
        "system_instruction": negotiator_system_prompt(ctx),
        "output_audio_transcription": {},
    }
    sup_cfg = {
        "response_modalities": ["AUDIO"],
        "system_instruction": supplier_system_prompt(ctx),
        "output_audio_transcription": {},
    }

    model = await resolve_model(client)
    async with client.aio.live.connect(model=model, config=neg_cfg) as neg, \
            client.aio.live.connect(model=model, config=sup_cfg) as sup:
        # Negotiator opens the call.
        prompt = "[The call has connected. Open the call now.]"
        speaker = "faultline_agent"
        for _ in range(max_turns):
            session = neg if speaker == "faultline_agent" else sup
            text, audio = await _one_turn(session, prompt)
            text = text.strip()
            if text:
                yield speaker, text, audio
            # hand the line to the other party as their input
            prompt = text or "[no response]"
            speaker = "supplier" if speaker == "faultline_agent" else "faultline_agent"
            if _looks_like_closing(text):
                break


async def _one_turn(session, user_text: str) -> tuple[str, bytes]:
    await session.send_client_content(
        turns={"role": "user", "parts": [{"text": user_text}]},
        turn_complete=True,
    )
    transcript_parts: list[str] = []
    audio = bytearray()
    async for msg in session.receive():
        if getattr(msg, "data", None):
            audio.extend(msg.data)
        sc = getattr(msg, "server_content", None)
        if sc is not None:
            ot = getattr(sc, "output_transcription", None)
            if ot and getattr(ot, "text", None):
                transcript_parts.append(ot.text)
            if getattr(sc, "turn_complete", False):
                break
    return "".join(transcript_parts).strip(), bytes(audio)


def _looks_like_closing(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in ("contingent on po", "thank you for your time", "we'll be in touch",
                                  "have a good", "goodbye", "good bye", "that's everything",
                                  "appreciate your time"))

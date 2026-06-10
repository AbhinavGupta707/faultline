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
from typing import AsyncIterator, Awaitable, Callable

from config import CONFIG
from personas import (
    CallContext,
    INTENT_SYSTEM_PROMPT,
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


def _send_audio(session, chunk: bytes):
    """Forward a PCM16/16k frame to the Live session, tolerant of SDK kwarg drift."""
    from google.genai import types

    blob = types.Blob(data=chunk, mime_type=_INPUT_MIME)
    try:
        return session.send_realtime_input(audio=blob)
    except TypeError:
        return session.send_realtime_input(media=blob)


# ──────────────────────────────────────────────────────────────────────────────
# Voice IN — transcribe push-to-talk audio and parse the intent in one Live turn.
# Runs in TEXT modality with input-audio transcription on: the transcription is the
# operator's words; the model's text reply is the JSON intent (system prompt in personas).
# ──────────────────────────────────────────────────────────────────────────────
async def transcribe_and_intent(
    audio_chunks: AsyncIterator[bytes],
    pending_approval_id: str | None,
    on_partial: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str, str]:
    """Returns (final_transcript, raw_model_text). Caller coerces raw text → voice_intent."""
    system = INTENT_SYSTEM_PROMPT
    if pending_approval_id:
        system += f"\n\nPENDING APPROVAL CONTEXT: approval_id to use for approve/reject = \"{pending_approval_id}\"."

    config = {
        "response_modalities": ["TEXT"],
        "system_instruction": system,
        "input_audio_transcription": {},
    }

    client = _client()
    transcript_parts: list[str] = []
    model_text_parts: list[str] = []

    async with client.aio.live.connect(model=CONFIG.live_model, config=config) as session:
        receiver = asyncio.create_task(
            _drain_intent(session, transcript_parts, model_text_parts, on_partial)
        )
        async for chunk in audio_chunks:
            if chunk:
                await _send_audio(session, chunk)
        # Signal end of the user's audio turn.
        try:
            await session.send_realtime_input(audio_stream_end=True)
        except TypeError:
            await session.send_client_content(turns=[], turn_complete=True)
        await receiver

    return "".join(transcript_parts).strip(), "".join(model_text_parts).strip()


async def _drain_intent(session, transcript_parts, model_text_parts, on_partial):
    async for msg in session.receive():
        sc = getattr(msg, "server_content", None)
        if sc is not None:
            it = getattr(sc, "input_transcription", None)
            if it and getattr(it, "text", None):
                transcript_parts.append(it.text)
                if on_partial:
                    await on_partial("".join(transcript_parts).strip())
            mt = getattr(sc, "model_turn", None)
            if mt and getattr(mt, "parts", None):
                for part in mt.parts:
                    if getattr(part, "text", None):
                        model_text_parts.append(part.text)
            if getattr(sc, "turn_complete", False):
                break
        # Some SDK builds expose text directly on the message.
        elif getattr(msg, "text", None):
            model_text_parts.append(msg.text)


# ──────────────────────────────────────────────────────────────────────────────
# Voice OUT — two-party negotiation call. Two Live AUDIO sessions (negotiator + supplier);
# each persona's turn is driven by the other party's transcribed line, giving deterministic
# turn-taking with natural native-audio voice. Yields (speaker, text, audio_bytes) per turn.
# ──────────────────────────────────────────────────────────────────────────────
async def run_negotiation_call(
    ctx: CallContext,
    max_turns: int = 6,
) -> AsyncIterator[tuple[str, str, bytes]]:
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

    async with client.aio.live.connect(model=CONFIG.live_model, config=neg_cfg) as neg, \
            client.aio.live.connect(model=CONFIG.live_model, config=sup_cfg) as sup:
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

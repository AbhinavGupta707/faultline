"""Gemini layer — structured output via google-genai, with a hard floor.

Design rule: every agent has a deterministic core that produces contract-valid
output from tool results alone; Gemini refines judgment fields (triage choices,
why_relevant, est_disruption_days, rationales, call scripts) when available.
`structured()` returns None on ANY failure — no creds, lib missing, quota,
schema mismatch — and callers fall back to the deterministic core. This is what
keeps the golden-path test runnable with zero cloud deps (GEMINI_MODE=off).
"""
from __future__ import annotations

import logging
import os
from typing import Optional, TypeVar

from pydantic import BaseModel

from agents import config

log = logging.getLogger("faultline.llm")
T = TypeVar("T", bound=BaseModel)

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def load_prompt(agent_name: str) -> str:
    try:
        with open(os.path.join(_PROMPTS_DIR, f"{agent_name}.md"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


class Gemini:
    def __init__(self) -> None:
        self._client = None

    def enabled(self) -> bool:
        if config.gemini_mode() == "off":
            return False
        if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GCP_PROJECT")):
            return False
        try:
            import google.genai  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is None:
            from google import genai
            if os.getenv("GCP_PROJECT"):
                self._client = genai.Client(
                    vertexai=True,
                    project=os.getenv("GCP_PROJECT"),
                    location=os.getenv("VERTEX_LOCATION", "us-central1"),
                )
            else:
                self._client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        return self._client

    async def structured(self, *, model: str, system: str, prompt: str,
                         schema: type[T]) -> Optional[T]:
        """One structured-output call; None on any failure (caller falls back)."""
        if not self.enabled():
            return None
        try:
            client = self._get_client()
            resp = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "system_instruction": system,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                },
            )
            return schema.model_validate_json(resp.text)
        except Exception as exc:
            log.warning("Gemini structured call failed (%s) — deterministic fallback", exc)
            return None

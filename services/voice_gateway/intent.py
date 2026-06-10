"""Intent parsing for voice-IN.

Two layers:
* ``rule_based_intent`` — deterministic keyword parser. Used in mock mode and as the
  always-available fallback if the model returns junk. Nails the action + approval routing
  for the scripted demo commands with zero cloud dependency.
* ``coerce_intent`` — validates/normalizes a model-produced JSON object into a contract
  ``voice_intent`` dict, filling ``approval_id`` from pending context for approve/reject.

Output shape is the frozen ``$defs/voice_intent`` (contracts/schemas/faultline.schema.json):
{action, confidence, approval_id?, product_id?, supplier_id?, text?}
"""
from __future__ import annotations

import json
import re

VALID_ACTIONS = {"query", "approve", "reject", "show", "whatif", "unknown"}

# Phrase → product_id lexicon. Best-effort focus hints for the map; ids align with the seed
# naming convention (Session A owns the canonical set — these are the demo lines).
_PRODUCT_LEXICON = {
    "cold-brew": "prod-cold-brew",
    "cold brew": "prod-cold-brew",
    "coffee": "prod-cold-brew",
    "granola": "prod-granola",
    "sparkling": "prod-sparkling",
    "botanical": "prod-sparkling",
}

_APPROVE_WORDS = ("approve", "approved", "go ahead", "confirm", "authorize", "authorise", "do it", "proceed", "sign off")
_REJECT_WORDS = ("reject", "decline", "deny", "cancel", "hold off", "don't", "do not", "veto", "no go")
_SHOW_WORDS = ("show", "focus", "zoom", "highlight", "take me to", "pull up", "display")
_QUERY_WORDS = ("what", "which", "how", "why", "when", "where", "who", "risk", "exposure", "status", "tell me")
_WHATIF_WORDS = ("what if", "what-if", "simulate", "scenario", "suppose", "imagine if")


def _product_hint(text: str) -> str | None:
    low = text.lower()
    for phrase, pid in _PRODUCT_LEXICON.items():
        if phrase in low:
            return pid
    return None


def rule_based_intent(transcript: str, pending_approval_id: str | None = None) -> dict:
    text = (transcript or "").strip()
    low = text.lower()
    if not low:
        return {"action": "unknown", "confidence": 0.0, "text": ""}

    intent: dict = {"text": text}

    # what-if first (it also contains "what")
    if any(w in low for w in _WHATIF_WORDS):
        intent.update(action="whatif", confidence=0.8)
        return intent

    if any(w in low for w in _APPROVE_WORDS):
        intent.update(action="approve", confidence=0.92)
        if pending_approval_id:
            intent["approval_id"] = pending_approval_id
        pid = _product_hint(low)
        if pid:
            intent["product_id"] = pid
        return intent

    if any(w in low for w in _REJECT_WORDS):
        intent.update(action="reject", confidence=0.9)
        if pending_approval_id:
            intent["approval_id"] = pending_approval_id
        return intent

    if any(low.startswith(w) or f" {w} " in f" {low} " for w in _SHOW_WORDS):
        intent.update(action="show", confidence=0.85)
        pid = _product_hint(low)
        if pid:
            intent["product_id"] = pid
        return intent

    if low.endswith("?") or any(low.startswith(w) for w in _QUERY_WORDS) or any(w in low for w in _QUERY_WORDS):
        intent.update(action="query", confidence=0.8)
        return intent

    intent.update(action="unknown", confidence=0.3)
    return intent


def coerce_intent(raw: str | dict, transcript: str, pending_approval_id: str | None = None) -> dict:
    """Normalize a model output (JSON string or dict) into a valid voice_intent.

    Falls back to the rule-based parser on any parse/validation failure so the gateway
    never emits a malformed intent.
    """
    obj: dict | None = None
    if isinstance(raw, dict):
        obj = raw
    elif isinstance(raw, str):
        obj = _extract_json(raw)

    if not isinstance(obj, dict):
        return rule_based_intent(transcript, pending_approval_id)

    action = str(obj.get("action", "")).lower().strip()
    if action not in VALID_ACTIONS:
        return rule_based_intent(transcript, pending_approval_id)

    try:
        confidence = float(obj.get("confidence", 0.6))
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))

    intent: dict = {"action": action, "confidence": confidence}
    intent["text"] = str(obj.get("text") or transcript or "").strip()

    for key in ("product_id", "supplier_id", "approval_id"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            intent[key] = val.strip()

    # approve/reject must carry the pending approval_id so the frontend can resolve it.
    if action in ("approve", "reject") and "approval_id" not in intent and pending_approval_id:
        intent["approval_id"] = pending_approval_id

    return intent


def _extract_json(s: str) -> dict | None:
    s = s.strip()
    # strip a ```json fence if the model added one
    fence = re.search(r"\{.*\}", s, re.DOTALL)
    if not fence:
        return None
    try:
        return json.loads(fence.group(0))
    except json.JSONDecodeError:
        return None

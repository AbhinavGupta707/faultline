"""Headless voice spike / self-check.

Usage:
    python spike.py              # offline self-check (no creds): contract plumbing PASS/FAIL
    python spike.py path.wav     # live mode: stream a 16 kHz mono WAV → Live → print intent

Offline mode validates that the gateway's mock outputs (intents + call events) conform to the
frozen schemas — the credential-free proof that voice-in and voice-out are wired correctly.
Live mode (VOICE_MODE=live + creds) performs the real mic→Live→intent round trip from a WAV.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import wave

try:  # Windows consoles default to cp1252 — make the glyphs printable everywhere.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from config import CONFIG, describe
from intent import rule_based_intent
import mock

DEMO_COMMANDS = [
    ("what's my biggest risk right now?", "query"),
    ("show the coffee chain", "show"),
    ("approve the re-source for the cold-brew line", "approve"),
    ("reject that", "reject"),
    ("what if Busan port closes for ten days", "whatif"),
]


def _load_schema():
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(6):
        p = os.path.join(cur, "contracts", "schemas", "faultline.schema.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        cur = os.path.dirname(cur)
    return None


def _validator(schema, defname):
    from jsonschema import Draft202012Validator

    root = {"$ref": f"#/$defs/{defname}", "$defs": schema["$defs"]}
    return Draft202012Validator(root)


def offline_selfcheck() -> int:
    print("── voice spike · OFFLINE self-check ──")
    print("config:", json.dumps(describe()))
    schema = _load_schema()
    failures = 0

    vi = _validator(schema, "voice_intent") if schema else None
    print("\nvoice-in intents (rule-based):")
    for text, expect in DEMO_COMMANDS:
        intent = rule_based_intent(text, pending_approval_id="apr-resource-coldbrew-01")
        ok = intent["action"] == expect
        if vi:
            errs = list(vi.iter_errors(intent))
            ok = ok and not errs
        flag = "✓" if ok else "✗"
        if not ok:
            failures += 1
        print(f"  {flag} {text!r} → {intent['action']} ({intent['confidence']:.2f})"
              f"{' approval_id=' + intent['approval_id'] if intent.get('approval_id') else ''}")

    ce = _validator(schema, "call_event_payload") if schema else None
    print("\nvoice-out call events (mock replay):")
    n = 0
    for ev in mock.load_call_transcript():
        ev = {**ev, "call_id": "call-spike-01"}
        n += 1
        if ce:
            errs = list(ce.iter_errors(ev))
            if errs:
                failures += 1
                print(f"  ✗ {ev.get('event')}: {errs[0].message}")
    print(f"  ✓ {n} call events validate against call_event_payload" if ce else f"  {n} events (schema not found)")

    print("\nRESULT:", "PASS — voice plumbing conforms to contract" if failures == 0
          else f"FAIL — {failures} issue(s)")
    return 1 if failures else 0


async def live_roundtrip(wav_path: str) -> int:
    import live  # lazy

    print("── voice spike · LIVE round-trip ──")
    print("config:", json.dumps(describe()))
    with wave.open(wav_path, "rb") as wf:
        assert wf.getframerate() == 16000 and wf.getnchannels() == 1, "need 16 kHz mono WAV"
        pcm = wf.readframes(wf.getnframes())

    async def chunks():
        for i in range(0, len(pcm), 3200):  # ~100 ms frames
            yield pcm[i:i + 3200]
            await asyncio.sleep(0.01)

    transcript, raw = await live.transcribe_and_intent(chunks(), pending_approval_id=None)
    print("transcript:", transcript)
    print("model intent:", raw)
    return 0


def main() -> int:
    if len(sys.argv) > 1:
        if not CONFIG.is_live:
            print("warning: a WAV was given but VOICE_MODE != live — set VOICE_MODE=live + creds")
        return asyncio.run(live_roundtrip(sys.argv[1]))
    return offline_selfcheck()


if __name__ == "__main__":
    raise SystemExit(main())

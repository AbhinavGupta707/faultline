"""Run-state assembly for the depth lane (Session G).

The depth agents (Briefer / Enricher / BQExport) read a small set of shared
session-state keys written by Session B's orchestrator (contracts/components.md §3):

    run_meta, relevant_events, exposure_paths, ranked_exposures,
    alternates, draft_po, verify_result

Until S1 hands us real run shapes, we build against the *golden* run assembled
from contracts/fixtures/ — the same incident the ws_replay scripts (Gujarat flood →
emulsifier secured). `RunState` is a thin, dict-backed view so it works identically
whether B hands us a live `session.state` mapping or we load the fixtures here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts" / "fixtures"

# The exact session-state keys depth agents may read (frozen, components.md §3).
STATE_KEYS = (
    "run_meta",
    "relevant_events",
    "exposure_paths",
    "ranked_exposures",
    "alternates",
    "draft_po",
    "verify_result",
)


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@dataclass
class RunState:
    """Read-only view over the depth session-state keys.

    Construct from a live mapping (`RunState(state)`) or from fixtures
    (`RunState.golden()`). Missing keys read back as None / empty — depth agents
    must degrade gracefully, never assume a fully-populated run.
    """

    state: dict[str, Any] = field(default_factory=dict)

    # --- accessors (None-safe) -------------------------------------------------
    @property
    def run_meta(self) -> dict[str, Any]:
        return self.state.get("run_meta") or {}

    @property
    def run_id(self) -> str:
        return self.run_meta.get("run_id") or "run-unknown"

    @property
    def mode(self) -> str:
        return self.run_meta.get("mode") or "live"

    @property
    def simulated(self) -> bool:
        return self.mode == "simulated"

    @property
    def relevant_events(self) -> list[dict[str, Any]]:
        return (self.state.get("relevant_events") or {}).get("events") or []

    @property
    def exposure_paths(self) -> list[dict[str, Any]]:
        return (self.state.get("exposure_paths") or {}).get("paths") or []

    @property
    def exposures(self) -> list[dict[str, Any]]:
        return (self.state.get("ranked_exposures") or {}).get("exposures") or []

    @property
    def alternates(self) -> dict[str, Any]:
        return self.state.get("alternates") or {}

    @property
    def draft_po(self) -> dict[str, Any]:
        return self.state.get("draft_po") or {}

    @property
    def verify_result(self) -> dict[str, Any]:
        return self.state.get("verify_result") or {}

    # --- derived facts (shared by Briefer / BQExport / analytics) --------------
    @property
    def root_event(self) -> dict[str, Any]:
        """The highest-severity relevant event = the run's root cause."""
        evs = self.relevant_events
        if not evs:
            return {}
        return max(evs, key=lambda e: e.get("severity_raw", 0.0))

    @property
    def all_evidence_event_ids(self) -> list[str]:
        seen: list[str] = []
        for e in self.relevant_events:
            eid = e.get("event_id")
            if eid and eid not in seen:
                seen.append(eid)
        return seen

    @property
    def dollars_at_risk_total(self) -> float:
        return float(sum(e.get("dollars_at_risk_usd", 0) for e in self.exposures))

    @property
    def dollars_at_risk_avoided(self) -> float:
        """$ averted = at-risk on exposures the run actually secured.

        Prefer the Verifier's verdict (gap_closed); fall back to status==secured.
        """
        vr = self.verify_result
        if vr.get("gap_closed"):
            target = vr.get("exposure_id")
            for e in self.exposures:
                if e.get("exposure_id") == target:
                    return float(e.get("dollars_at_risk_usd", 0))
        return float(
            sum(e.get("dollars_at_risk_usd", 0) for e in self.exposures if e.get("status") == "secured")
        )

    @property
    def secured(self) -> bool:
        return bool(self.verify_result.get("gap_closed"))

    @classmethod
    def golden(cls) -> "RunState":
        """Assemble the canonical Gujarat-flood run from contracts/fixtures/."""
        return cls(
            {
                "run_meta": {
                    "run_id": "run-2026-06-10-0001",
                    "mode": "live",
                    "started_at": "2026-06-10T09:00:00Z",
                },
                "relevant_events": _load("relevant_events.json"),
                "exposure_paths": _load("exposure_paths.json"),
                "ranked_exposures": _load("ranked_exposures.json"),
                "alternates": _load("alternates.json"),
                "draft_po": _load("draft_po.json"),
                "verify_result": _load("verify_result.json"),
            }
        )


if __name__ == "__main__":
    rs = RunState.golden()
    print(
        f"golden run {rs.run_id} mode={rs.mode} "
        f"exposures={len(rs.exposures)} at_risk=${rs.dollars_at_risk_total:,.0f} "
        f"avoided=${rs.dollars_at_risk_avoided:,.0f} secured={rs.secured} "
        f"root={rs.root_event.get('event_id')}"
    )

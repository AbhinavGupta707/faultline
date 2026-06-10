"""RunContext — everything one pipeline run carries between agents.

`state` holds the EXACT shared session-state keys from contracts/components.md §3
(run_meta, relevant_events, exposure_paths, ranked_exposures, alternates,
draft_po, verify_result) that depth agents (Session G) read. Keys prefixed `_`
are Session B internals and not part of that contract.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from agents.approvals import ApprovalRegistry
from agents.bus import Bus
from agents.llm import Gemini
from agents.schemas import WhatifScenario
from agents.tools.elastic_mcp import ToolBelt


def short_id() -> str:
    return uuid.uuid4().hex[:4]


@dataclass
class RunContext:
    run_id: str
    mode: str  # "live" | "simulated"
    bus: Bus
    tools: ToolBelt
    llm: Gemini
    approvals: ApprovalRegistry
    state: dict[str, Any] = field(default_factory=dict)
    scenario: Optional[WhatifScenario] = None
    focus_event_id: Optional[str] = None      # what-if: the synthetic event id
    exclude_event_ids: set = field(default_factory=set)
    _decision_seq: int = 0

    @property
    def simulated(self) -> bool:
        return self.mode == "simulated"

    def next_decision_id(self) -> str:
        self._decision_seq += 1
        return f"dec-{self.run_id.removeprefix('run-')}-{self._decision_seq:04d}"

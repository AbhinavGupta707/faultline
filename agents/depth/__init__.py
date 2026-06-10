"""Depth-agent registry — the B↔G isolation boundary (contracts/components.md §3).

Session G fills this list (Briefer, Enricher, BQExport). Session B's orchestrator
iterates it after Verify and must behave identically when it is empty.
SHIPS EMPTY at phase0 — Session B never edits this package.
"""

DEPTH_AGENTS: list = []

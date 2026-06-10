"""Depth-agent registry — the B↔G isolation boundary (contracts/components.md §3).

`DEPTH_AGENTS` is the ONE symbol Session B imports. It ships as a list of ADK agents
(Briefer, Enricher, BQExport) that B's orchestrator iterates after Verify, behaving
identically whether the list is empty or full. The ADK wrappers are built only when
`google.adk` is importable (it is at integration time); until then DEPTH_AGENTS stays
empty and the same functionality is reachable — and fully tested — through the pure
functions below and the standalone server (serve.py). This guarantees `import
agents.depth` never drags in heavy/optional deps or raises into B's core loop.

Each depth agent reads the shared session-state keys (run_meta, relevant_events,
exposure_paths, ranked_exposures, alternates, draft_po, verify_result) and:
  • Briefer  → emits `brief`, writes the report to GCS, writes a kind:"brief" decision,
               and stores its payload on state["brief"].
  • Enricher → re-emits `ranked_exposures` (enriched:true), kind:"enrich" decision,
               and updates state["ranked_exposures"].
  • BQExport → streams the run to BigQuery (no emit), kind tracked in warehouse only.

HTTP: `router` (api.py) carries GET /analytics/summary + GET /report/{run_id}; B mounts
it with `app.include_router(agents.depth.router)`. See HANDOFF.md for the wiring recipe.
"""
from __future__ import annotations

from typing import Any, Callable

from .api import router  # noqa: F401  (re-exported for B to mount)
from .bq_export import export_run
from .briefer import run_briefer
from .enrich import run_enricher
from .runstate import RunState

__all__ = ["DEPTH_AGENTS", "DEPTH_TASKS", "run_all_depth", "router"]


# ── pure-function task registry (backend-agnostic, fully tested) ────────────────────
# Each task: (name, fn(state_dict, emit) -> writes results back into state_dict).
def _briefer_task(state: dict[str, Any], emit: Callable[[str, dict], None] | None) -> None:
    res = run_briefer(RunState(state), emit=emit)
    state["brief"] = res.payload
    state.setdefault("_decisions", []).append(res.decision)


def _enricher_task(state: dict[str, Any], emit: Callable[[str, dict], None] | None) -> None:
    res = run_enricher(RunState(state), emit=emit)
    state["ranked_exposures"] = res.payload  # refined re-emit (enriched:true)
    state.setdefault("_decisions", []).append(res.decision)


def _bqexport_task(state: dict[str, Any], emit: Callable[[str, dict], None] | None) -> None:
    decisions = state.get("_decisions")
    export_run(RunState(state), decisions=decisions)


DEPTH_TASKS: list[tuple[str, Callable[[dict, Any], None]]] = [
    ("briefer", _briefer_task),
    ("enricher", _enricher_task),
    ("bqexport", _bqexport_task),
]


def run_all_depth(state: dict[str, Any], emit: Callable[[str, dict], None] | None = None) -> dict[str, Any]:
    """Run every depth task over a shared state dict, never raising into the caller.

    The exception-isolation contract: a failing depth task is logged and skipped, the
    core loop is unaffected. Returns the (mutated) state for convenience.
    """
    for name, fn in DEPTH_TASKS:
        try:
            fn(state, emit)
        except Exception as exc:  # pragma: no cover - defensive, never propagate
            import logging

            logging.getLogger("faultline.depth").warning("depth task %s failed: %s", name, exc)
    return state


# ── ADK agent wrappers (built only when google.adk is available) ────────────────────
def _build_adk_agents() -> list:
    try:
        from google.adk.agents import BaseAgent
        from google.adk.events import Event
    except Exception:
        return []

    def _make(agent_name: str, task: Callable[[dict, Any], None]):
        class _DepthAgent(BaseAgent):  # type: ignore[misc]
            name: str = agent_name

            async def _run_async_impl(self, ctx):  # noqa: ANN001
                # Side-effect agent: reads/writes ctx.session.state, never blocks the loop.
                # Emissions are buffered onto state["_emits"] so B can replay them as
                # ws `agent.emit` messages through its Runner callback (HANDOFF.md).
                def _emit(kind, payload):
                    ctx.session.state.setdefault("_emits", []).append({"kind": kind, "payload": payload})

                try:
                    task(ctx.session.state, _emit)
                except Exception as exc:  # pragma: no cover
                    import logging

                    logging.getLogger("faultline.depth").warning(
                        "depth agent %s failed: %s", agent_name, exc
                    )
                if False:  # this is a side-effect agent; it yields no events itself
                    yield Event(author=agent_name)  # pragma: no cover

        return _DepthAgent(name=agent_name)

    return [_make(name, fn) for name, fn in DEPTH_TASKS]


DEPTH_AGENTS: list = _build_adk_agents()

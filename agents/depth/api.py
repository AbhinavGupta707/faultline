"""Depth HTTP routes — GET /analytics/summary and GET /report/{run_id}.

These two routes are specified in contracts/http_api.md as "Session G registers the
implementation; the route lives on the agent runtime." We expose them as a FastAPI
`APIRouter` so Session B's main.py mounts the whole lane with one line
(`app.include_router(depth_api.router)`) without editing anything in agents/depth/, and
so the lane is independently runnable via serve.py before B is ready (see HANDOFF.md).
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from .analytics import summarize
from .artifacts import ArtifactStore
from .briefer import produce_brief
from .runstate import RunState

router = APIRouter()

_CACHE_TTL = 60.0
_cache: dict[int, tuple[float, dict[str, Any]]] = {}


@router.get("/analytics/summary")
def analytics_summary(window: int = 60) -> JSONResponse:
    now = time.time()
    hit = _cache.get(window)
    if hit and (now - hit[0]) < _CACHE_TTL:
        return JSONResponse(hit[1], headers={"x-cache": "hit"})
    body = summarize(window)
    _cache[window] = (now, body)
    return JSONResponse(body, headers={"x-cache": "miss"})


def _ensure_golden_report(run_id: str, store: ArtifactStore) -> bool:
    """For dev/demo: materialize the golden report on first request if absent."""
    if store.exists(f"reports/by-run/{run_id}.pdf"):
        return True
    golden = RunState.golden()
    if golden.run_id == run_id:
        produce_brief(golden, store=store)
        return True
    return False


@router.get("/report/{run_id}")
def report(run_id: str, format: str = "pdf") -> Response:
    store = ArtifactStore()
    if not _ensure_golden_report(run_id, store):
        return JSONResponse({"error": "report not ready"}, status_code=404)
    if format == "md":
        data = store.read(f"reports/by-run/{run_id}.md")
        return Response(content=data or b"", media_type="text/markdown")
    data = store.read(f"reports/by-run/{run_id}.pdf")
    if data is None:
        return JSONResponse({"error": "report not ready"}, status_code=404)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{run_id}.pdf"'},
    )

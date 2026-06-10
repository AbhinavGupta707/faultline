"""Standalone dev server for the depth lane (independent of Session B's runtime).

Lets Session G run /analytics/summary and /report/{run_id} alone — the Analytics panel
points VITE_API_BASE here until B mounts depth_api.router in the real agent runtime.

    uvicorn agents.depth.serve:app --port 8090
    curl localhost:8090/analytics/summary | jq .
    curl -L localhost:8090/report/run-2026-06-10-0001 -o brief.pdf
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router

app = FastAPI(title="faultline-depth")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
def health():
    return {"ok": True, "service": "faultline-depth"}

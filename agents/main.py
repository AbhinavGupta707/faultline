"""Faultline agent runtime — FastAPI app: agent pipeline + WebSocket bridge.

Surface per contracts/http_api.md: GET /health, GET /ws, POST /whatif,
POST /approval. Every plan step, tool call, emission, decision and approval
request the pipeline produces is published on the Bus and streamed to every
/ws client per contracts/ws_protocol.md.

Control loop (impl plan §6): an asyncio task polls world-events every
POLL_INTERVAL_S (un-narrated) and starts a narrated run when fresh relevant
events appear; POST /whatif and ws whatif.run trigger on-demand simulated runs
through the identical pipeline (synthetic event flagged simulated:true).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from agents import config, orchestrator
from agents.approvals import ApprovalRegistry
from agents.bus import Bus, now_iso
from agents.context import RunContext
from agents.llm import Gemini
from agents.schemas import WhatifScenario
from agents.tools.elastic_mcp import ToolBelt
from agents.tools.po import generate_po_pdf

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("faultline.main")


class AppState:
    def __init__(self) -> None:
        self.bus = Bus()
        self.approvals = ApprovalRegistry()
        self.tools = ToolBelt(self.bus)
        self.tools.register_local("generate_po_pdf", generate_po_pdf)
        self.llm = Gemini()
        self.run_lock = asyncio.Lock()
        self.run_seq = 0
        self.seen_event_ids: set[str] = set()
        self.active_run_id: Optional[str] = None
        self.active_ctx: Optional[RunContext] = None
        self.last_relevant_ids: set[str] = set()
        self.events_cache: Optional[tuple[float, int, list[dict]]] = None  # (mono_ts, limit, docs)
        self.elastic_ok: bool = config.elastic_mode() == "mock"
        self.tasks: list[asyncio.Task] = []

    def next_run_id(self) -> str:
        self.run_seq += 1
        return f"run-{date.today().isoformat()}-{self.run_seq:04d}"


STATE = AppState()


# ── run management ───────────────────────────────────────────────
async def _execute_run(run_id: str, mode: str, scenario: Optional[WhatifScenario],
                       focus_event_id: Optional[str],
                       focus_event: Optional[dict] = None) -> None:
    async with STATE.run_lock:
        STATE.active_run_id = run_id
        ctx = RunContext(
            run_id=run_id, mode=mode, bus=STATE.bus, tools=STATE.tools,
            llm=STATE.llm, approvals=STATE.approvals, scenario=scenario,
            focus_event_id=focus_event_id, focus_event=focus_event,
            exclude_event_ids=set(STATE.seen_event_ids),
        )
        STATE.active_ctx = ctx  # /events/recent flags relevant events mid-run
        try:
            await orchestrator.run_pipeline(ctx)
        except Exception as exc:
            log.exception("run %s failed", run_id)
            STATE.bus.status(run_id, mode=mode, feeds_ok=True,
                             elastic_ok=STATE.elastic_ok, active_run_id=run_id,
                             note=f"Run failed: {str(exc)[:200]}")
        finally:
            relevant = ctx.state.get("relevant_events", {}).get("events", [])
            STATE.seen_event_ids.update(e["event_id"] for e in relevant)
            if relevant:
                STATE.last_relevant_ids = {e["event_id"] for e in relevant}
            if focus_event_id:
                STATE.seen_event_ids.add(focus_event_id)
            STATE.active_ctx = None
            STATE.active_run_id = None


def start_run(mode: str, scenario: Optional[WhatifScenario] = None,
              focus_event_id: Optional[str] = None,
              focus_event: Optional[dict] = None) -> str:
    run_id = STATE.next_run_id()
    task = asyncio.get_running_loop().create_task(
        _execute_run(run_id, mode, scenario, focus_event_id, focus_event))
    STATE.tasks.append(task)
    STATE.tasks[:] = [t for t in STATE.tasks if not t.done()]
    return run_id


# ── what-if plumbing ─────────────────────────────────────────────
def _rough_region(lat: float, lon: float) -> str:
    if -90 <= lon <= -30 and lat < 15:
        return "latam"
    if -130 <= lon <= -55 and lat >= 15:
        return "north-america"
    if -15 <= lon <= 40 and lat >= 35:
        return "western-europe"
    if 25 <= lon <= 60 and 10 <= lat < 38:
        return "middle-east"
    if 60 <= lon < 95:
        return "south-asia"
    if 95 <= lon <= 150 and lat < 12:
        return "southeast-asia"
    if 95 <= lon <= 150:
        return "east-asia"
    return "global"


def scenario_to_event(scenario: WhatifScenario) -> dict:
    title = scenario.title or (f"{scenario.event_type.replace('_', ' ')} scenario near "
                               f"{scenario.place_name or 'the selected location'}")
    if not title.upper().startswith("SIMULATED"):
        title = f"SIMULATED: {title}"
    return {
        "id": f"evt-whatif-{scenario.preset or 'custom'}-{uuid.uuid4().hex[:6]}",
        "source": "whatif",
        "title": title,
        "summary": (f"What-if scenario: {scenario.event_type.replace('_', ' ')} lasting "
                    f"{scenario.duration_days:g} days at magnitude {scenario.magnitude:.2f}."),
        "event_type": scenario.event_type,
        "location": scenario.location.wire(),
        "place_name": scenario.place_name or "Simulated location",
        "region": _rough_region(scenario.location.lat, scenario.location.lon),
        "severity_raw": scenario.magnitude,
        "published_at": now_iso(),
        "url": "",
        "simulated": True,
    }


async def _write_world_event(doc: dict) -> None:
    if config.elastic_mode() == "mock":
        from agents.mocks import elastic_fake
        elastic_fake.write_world_event(doc)
        return
    es = config.elasticsearch_url()
    if not es:
        raise HTTPException(
            status_code=503,
            detail={"error": "ELASTICSEARCH_URL not configured — cannot index what-if events in live mode"},
        )
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.put(
            f"{es}/{config.events_index()}/_doc/{doc['id']}?refresh=wait_for",
            json=doc, headers={"Authorization": f"ApiKey {config.elastic_api_key()}"},
        )
        resp.raise_for_status()


async def launch_whatif(scenario: WhatifScenario) -> tuple[str, str]:
    event = scenario_to_event(scenario)
    await _write_world_event(event)
    run_id = start_run("simulated", scenario=scenario,
                       focus_event_id=event["id"], focus_event=event)
    return run_id, event["id"]


# ── control loop ─────────────────────────────────────────────────
async def control_loop() -> None:
    await asyncio.sleep(3)  # let startup settle, then give the demo immediate life
    while True:
        try:
            if not STATE.run_lock.locked():
                if config.elastic_mode() == "live":
                    STATE.elastic_ok = await STATE.tools.healthcheck()
                out = await STATE.tools.quiet_call(
                    "search_events",
                    {"query": "supply chain disruption near supplier regions", "size": 50},
                )
                fresh = [
                    e for e in out.get("events", [])
                    if not e.get("simulated")
                    and e["id"] not in STATE.seen_event_ids
                    and e.get("severity_raw", 0) >= 0.5
                ]
                if fresh:
                    log.info("control loop: %d fresh events → starting run", len(fresh))
                    start_run("live")
        except Exception as exc:
            log.warning("control loop tick failed: %s", exc)
        await asyncio.sleep(config.poll_interval_s())


# ── FastAPI app ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.control_loop_enabled():
        STATE.tasks.append(asyncio.get_running_loop().create_task(control_loop()))
    yield
    for t in STATE.tasks:
        t.cancel()


app = FastAPI(title="faultline-agent", lifespan=lifespan)

# The web SPA is served from a different Cloud Run origin, so its browser fetch of
# /analytics/summary (and /events/recent, /report) needs CORS. Without this the fetch
# is silently blocked and the Analytics panel falls back to its bundled fixture.
# Public, read-only GETs with no credentials → allow_origins=["*"] is safe. (WS is exempt.)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Session G's depth routes (GET /analytics/summary, GET /report/{run_id}) — the
# phase0 registry has no router; the merged depth lane provides one (HANDOFF.md).
try:
    import agents.depth as _depth
    if hasattr(_depth, "router"):
        app.include_router(_depth.router)
except Exception as _exc:  # depth must never break the runtime
    log.warning("depth router not mounted: %s", _exc)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "faultline-agent",
        "mode": config.elastic_mode(),
        "elastic_ok": STATE.elastic_ok,
        "version": config.version(),
    }


EVENTS_CACHE_TTL_S = 30


def _current_relevant_ids() -> set[str]:
    """Event ids the current run's Watcher flagged (live mid-run), falling back
    to the last completed run's."""
    ctx = STATE.active_ctx
    if ctx is not None:
        events = (ctx.state.get("relevant_events") or {}).get("events")
        if events:
            return {e["event_id"] for e in events}
    return STATE.last_relevant_ids


async def _fetch_recent_events(limit: int) -> list[dict]:
    """Raw world_event docs, newest first, simulated excluded."""
    if config.elastic_mode() == "mock":
        from agents.mocks import elastic_fake
        docs = elastic_fake.search_events("", include_simulated=False, size=200)["events"]
    else:
        import httpx
        es = config.elasticsearch_url()
        if not es:
            raise RuntimeError("ELASTICSEARCH_URL not configured")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{es}/{config.events_index()}/_search",
                json={
                    "size": limit,
                    "sort": [{"published_at": "desc"}],
                    "query": {"bool": {"must_not": [{"term": {"simulated": True}}]}},
                    "_source": ["id", "title", "source", "published_at", "place_name",
                                "location", "severity_raw", "url"],
                },
                headers={"Authorization": f"ApiKey {config.elastic_api_key()}"},
            )
            resp.raise_for_status()
            docs = [h["_source"] for h in resp.json()["hits"]["hits"]]
    return sorted(docs, key=lambda d: d.get("published_at", ""), reverse=True)[:limit]


@app.get("/events/recent")
async def events_recent(limit: int = 25):
    """Additive polling endpoint (UI hits ~every 60s): newest live world events,
    with relevant:true on ids the current/last run's Watcher flagged. The fetch
    is cached 30s; relevant flags are computed fresh on every request."""
    limit = max(1, min(100, limit))
    now = time.monotonic()
    cache = STATE.events_cache
    if cache is not None and now - cache[0] < EVENTS_CACHE_TTL_S and limit <= cache[1]:
        docs = cache[2][:limit]
    else:
        try:
            docs = await _fetch_recent_events(limit)
            STATE.events_cache = (now, limit, docs)
        except Exception as exc:
            log.warning("/events/recent fetch failed: %s", exc)
            if cache is not None:  # stale beats empty for a polling endpoint
                docs = cache[2][:limit]
            else:
                raise HTTPException(status_code=503,
                                    detail={"error": f"events fetch failed: {str(exc)[:200]}"})
    relevant = _current_relevant_ids()
    return [
        {
            "id": d["id"],
            "title": d["title"],
            "source": d["source"],
            "published_at": d["published_at"],
            "place_name": d.get("place_name", ""),
            "lat": d["location"]["lat"],
            "lon": d["location"]["lon"],
            "severity": d["severity_raw"],
            "url": d.get("url") or "",
            "relevant": d["id"] in relevant,
        }
        for d in docs
    ]


@app.post("/whatif")
async def whatif(body: dict):
    scenario_raw = body.get("scenario")
    if not scenario_raw:
        raise HTTPException(status_code=400, detail={"error": "missing scenario"})
    try:
        scenario = WhatifScenario.model_validate(scenario_raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": f"invalid scenario: {exc}"})
    run_id, event_id = await launch_whatif(scenario)
    return JSONResponse(status_code=202,
                        content={"accepted": True, "run_id": run_id, "event_id": event_id})


@app.post("/approval")
async def approval(body: dict):
    approval_id = body.get("approval_id", "")
    if "approved" not in body:
        raise HTTPException(status_code=400, detail={"error": "missing approved"})
    applied = STATE.approvals.resolve(approval_id, bool(body["approved"]), body.get("note"))
    return {"ok": True, "approval_id": approval_id, "applied": applied}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    q = STATE.bus.subscribe()
    seq = 0

    async def send(msg: dict) -> None:
        nonlocal seq
        await websocket.send_text(json.dumps({**msg, "seq": seq}))
        seq += 1

    try:
        await send({
            "type": "status", "ts": now_iso(), "run_id": None,
            "payload": {
                "mode": "live", "feeds_ok": True, "elastic_ok": STATE.elastic_ok,
                "active_run_id": STATE.active_run_id,
                "note": f"Faultline control tower online ({config.elastic_mode()} mode)",
            },
        })
        # reconnect mid-run: replay the active run's narration so the story survives a refresh
        if STATE.active_run_id:
            for msg in STATE.bus.run_history(STATE.active_run_id):
                await send(msg)

        async def sender() -> None:
            while True:
                await send(await q.get())

        async def receiver() -> None:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await _handle_client_message(msg)

        sender_task = asyncio.create_task(sender())
        receiver_task = asyncio.create_task(receiver())
        done, pending = await asyncio.wait(
            {sender_task, receiver_task}, return_when=asyncio.FIRST_EXCEPTION)
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        STATE.bus.unsubscribe(q)


async def _handle_client_message(msg: dict) -> None:
    """Client→server per contracts/ws_protocol.md."""
    mtype = msg.get("type")
    payload = msg.get("payload") or {}
    if mtype == "approval.decision":
        STATE.approvals.resolve(payload.get("approval_id", ""),
                                bool(payload.get("approved")), payload.get("note"))
    elif mtype == "whatif.run":
        try:
            scenario = WhatifScenario.model_validate(payload.get("scenario") or {})
            await launch_whatif(scenario)
        except HTTPException:
            raise
        except Exception as exc:
            log.warning("invalid whatif.run scenario: %s", exc)
    elif mtype == "voice.intent":
        intent = payload.get("intent") or {}
        action = intent.get("action")
        if action in ("approve", "reject"):
            approval_id = intent.get("approval_id")
            if not approval_id:
                pending = STATE.approvals.pending_ids()
                approval_id = pending[0] if pending else None
            if approval_id:
                STATE.approvals.resolve(approval_id, action == "approve",
                                        f"voice: {payload.get('transcript', '')[:120]}")
    elif mtype == "chat":
        text = (payload.get("text") or "").lower()
        if "scan" in text or "check" in text:
            if not STATE.run_lock.locked():
                start_run("live")
        else:
            STATE.bus.status(STATE.active_run_id, mode="live", feeds_ok=True,
                             elastic_ok=STATE.elastic_ok,
                             active_run_id=STATE.active_run_id,
                             note=f'Received: "{payload.get("text", "")[:140]}"')

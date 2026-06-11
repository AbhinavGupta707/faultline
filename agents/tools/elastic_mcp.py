"""Elastic tool dispatch — mock (fixtures) or live (Agent Builder MCP server).

Two things live here (impl plan §3.3):

1. `ToolBelt` — the narrated dispatcher the pipeline uses. EVERY call publishes
   `tool.call` messages on the bus (Elastic MCP tools flagged elastic:true so the
   UI renders the distinct chip). ELASTIC_MODE=mock routes to
   agents/mocks/elastic_fake.py (identical names/signatures); live routes to
   {KIBANA_URL}/api/agent_builder/mcp over streamable HTTP.
2. `build_adk_toolset()` — the documented ADK McpToolset wiring, for running the
   agents as ADK LlmAgents against the same endpoint.

write_decision follows the contract's fast-call rule: a single status:"ok"
message with no preceding "start".
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

from agents import config
from agents.bus import Bus
from agents.mocks import elastic_fake

ELASTIC_TOOL_NAMES = [
    "search_events",
    "match_event_to_suppliers",
    "traverse_supply_graph",
    "lookup_exposure",
    "find_alternate_suppliers",
    "write_decision",
]

# Tools that pair start/ok on the UI; write_decision is a fast single-ok call.
_FAST_TOOLS = {"write_decision"}


class ToolError(RuntimeError):
    pass


class ToolBelt:
    def __init__(self, bus: Bus) -> None:
        self.bus = bus
        self._local_tools: dict[str, Callable[..., Awaitable[dict]]] = {}

    def register_local(self, name: str, fn: Callable[..., Awaitable[dict]]) -> None:
        """Non-Elastic tools (e.g. generate_po_pdf) still narrate via tool.call."""
        self._local_tools[name] = fn

    async def call(self, *, run_id: str, agent: str, tool: str, args: dict,
                   args_summary: str) -> dict:
        elastic = tool in ELASTIC_TOOL_NAMES
        call_id = f"tc-{uuid.uuid4().hex[:8]}"
        if tool not in _FAST_TOOLS:
            self.bus.tool_call(run_id, call_id=call_id, agent=agent, tool=tool,
                               args_summary=args_summary, status="start", elastic=elastic)
        t0 = time.perf_counter()
        try:
            result = await self._dispatch(tool, args)
        except Exception as exc:
            self.bus.tool_call(run_id, call_id=call_id, agent=agent, tool=tool,
                               args_summary=args_summary, status="err", elastic=elastic,
                               latency_ms=(time.perf_counter() - t0) * 1000, error=str(exc)[:300])
            raise ToolError(f"{tool} failed: {exc}") from exc
        self.bus.tool_call(run_id, call_id=call_id, agent=agent, tool=tool,
                           args_summary=args_summary, status="ok", elastic=elastic,
                           latency_ms=(time.perf_counter() - t0) * 1000)
        return result

    async def quiet_call(self, tool: str, args: dict) -> dict:
        """Un-narrated dispatch — control-loop polling only, never inside a run."""
        return await self._dispatch(tool, args)

    async def healthcheck(self) -> bool:
        if config.elastic_mode() == "mock":
            return True
        try:
            tools = await asyncio.wait_for(_mcp_list_tools(), timeout=5)
            return len(tools) > 0
        except Exception:
            return False

    async def _dispatch(self, tool: str, args: dict) -> dict:
        if tool in self._local_tools:
            return await self._local_tools[tool](args)
        if tool not in ELASTIC_TOOL_NAMES:
            raise ToolError(f"unknown tool: {tool}")
        if config.elastic_mode() == "mock":
            fn = getattr(elastic_fake, tool)
            return fn(**args)
        return await live_call(tool, args)


# ── live result adapter (elastic/tools/INTEGRATION.md) ──────────────────────
# Agent Builder tools return {"results":[{type:"esql_results","data":{columns,values}}]}
# (write_decision returns a workflow execution record). The adapter reshapes
# real envelopes into the FROZEN contract output shapes the mock already speaks.

# Params the live tools REQUIRE even though the contract marks them defaulted.
_REQUIRED_DEFAULTS: dict[str, dict] = {
    "search_events": {"size": 20},
    "match_event_to_suppliers": {"size": 10},
    "find_alternate_suppliers": {"size": 5},
}


def _esql_rows(payload: dict) -> list[dict]:
    for block in payload.get("results", []):
        if block.get("type") == "esql_results":
            data = block["data"]
            names = [c["name"] for c in data["columns"]]
            return [dict(zip(names, row)) for row in data["values"]]
    return []


def _as_list(value) -> list:
    """ES|QL multivalue columns arrive as null / scalar / list — normalize."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _strip_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _supplier_from_row(row: dict) -> dict:
    sup = _strip_none({k: row.get(k) for k in (
        "supplier_id", "name", "tier", "country", "region", "lead_time_days",
        "expedited_lead_time_days", "capacity", "profile_semantic")})
    sup["location"] = {"lat": row["lat"], "lon": row["lon"]}
    sup["components"] = _as_list(row.get("components"))
    sup["alternate_for"] = _as_list(row.get("alternate_for"))
    sup["certifications"] = _as_list(row.get("certifications"))
    return sup


def reshape(tool: str, args: dict, payload: dict) -> dict:
    if tool == "write_decision":
        execution = (payload.get("results") or [{}])[0].get("data", {}).get("execution", {})
        status = execution.get("status")
        error = execution.get("error_message") or ""
        # The workflow indexes with create-semantics (_id = decision_id), so a
        # duplicate write fails with version_conflict. The CONTRACT defines the
        # tool as idempotent on decision_id — a duplicate IS the success case.
        if status != "completed" and "version_conflict" not in error:
            raise ToolError(f"write_decision workflow {status}: {error[:200]}")
        return {"acknowledged": True, "decision_id": args.get("decision_id", ""),
                "index": "decision-log"}

    rows = _esql_rows(payload)

    if tool == "search_events":
        events = []
        for row in rows:
            ev = _strip_none({k: row.get(k) for k in (
                "id", "source", "title", "summary", "event_type", "place_name",
                "region", "severity_raw", "published_at", "url", "simulated")})
            ev["location"] = {"lat": row["lat"], "lon": row["lon"]}
            ev.setdefault("simulated", False)
            events.append(ev)
        return {"events": events, "total": len(events)}

    if tool == "match_event_to_suppliers":
        return {"matches": [
            {"supplier": _supplier_from_row(row), "score": row["score"],
             "signals": _strip_none({"semantic_score": row.get("semantic_score")})}
            for row in rows
        ]}

    if tool == "traverse_supply_graph":
        paths = []
        for row in rows:
            paths.append(_strip_none({
                "path_id": row.get("path_id"),
                "root_supplier_id": row["root_supplier_id"],
                "supplier_chain": json.loads(row["supplier_chain_json"]),
                "component_id": row["component_id"],
                "component_name": row.get("component_name"),
                "product_id": row["product_id"],
                "product_name": row.get("product_name"),
                "hops": row["hops"],
                "route_via": row.get("route_via"),
            }))
        return {"paths": paths}

    if tool == "lookup_exposure":
        component_ids = args.get("component_ids")  # contract filter, not applied server-side
        return {"exposures": [
            _strip_none(row) for row in rows
            if not component_ids or row["component_id"] in component_ids
        ]}

    if tool == "find_alternate_suppliers":
        constraints = args.get("constraints") or {}  # ignored server-side — apply here
        exclude = set(constraints.get("exclude_supplier_ids") or [])
        required_certs = set(constraints.get("required_certifications") or [])
        cap_order = ["low", "medium", "high"]
        out = []
        for row in rows:
            sup = _supplier_from_row(row)
            if sup["supplier_id"] in exclude:
                continue
            if required_certs and not required_certs.issubset(set(sup["certifications"])):
                continue
            if constraints.get("min_capacity") and \
                    cap_order.index(sup["capacity"]) < cap_order.index(constraints["min_capacity"]):
                continue
            if constraints.get("max_lead_time_days") is not None:
                effective = sup.get("expedited_lead_time_days") or sup["lead_time_days"]
                if effective > constraints["max_lead_time_days"]:
                    continue
            out.append({"supplier": sup, "score": row["score"]})
        return {"alternates": out}

    raise ToolError(f"no reshape for tool: {tool}")


async def live_call(tool: str, args: dict) -> dict:
    """Contract-shaped call against the live Agent Builder tools."""
    wire_args = {**_REQUIRED_DEFAULTS.get(tool, {}), **args}
    if tool == "write_decision":
        wire_args = {"doc_json": json.dumps(args)}
    payload = await _mcp_call(tool, wire_args)
    return reshape(tool, args, payload)


# ── live MCP plumbing (lazy imports — mock mode has zero cloud deps) ─────────
def _mcp_endpoint() -> str:
    base = config.kibana_url()
    if not base:
        raise ToolError("KIBANA_URL not set — cannot use ELASTIC_MODE=live")
    return f"{base}/api/agent_builder/mcp"


def _mcp_headers() -> dict[str, str]:
    return {"Authorization": f"ApiKey {config.elastic_api_key()}"}


async def _mcp_call(tool: str, args: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(_mcp_endpoint(), headers=_mcp_headers()) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            if result.isError:
                raise ToolError(f"MCP error from {tool}: {result.content}")
            # Agent Builder returns JSON in the first text content block.
            for block in result.content:
                if getattr(block, "type", "") == "text":
                    return json.loads(block.text)
            structured = getattr(result, "structuredContent", None)
            if structured:
                return structured
            raise ToolError(f"{tool} returned no parsable content")


async def _mcp_list_tools() -> list:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(_mcp_endpoint(), headers=_mcp_headers()) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return listed.tools


def build_adk_toolset():
    """Impl plan §3.3 snippet — McpToolset for running agents as ADK LlmAgents."""
    from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=_mcp_endpoint(),
            headers=_mcp_headers(),
        ),
        tool_filter=ELASTIC_TOOL_NAMES,
    )


if __name__ == "__main__":
    # S1 readiness probe: `KIBANA_URL=… ELASTIC_API_KEY=… python -m agents.tools.elastic_mcp`
    # Lists the tools published at the MCP endpoint, flags contract-name mismatches,
    # and runs one search_events round-trip.
    async def _probe() -> None:
        print(f"probing {_mcp_endpoint()} …")
        tools = await _mcp_list_tools()
        names = [t.name for t in tools]
        print(f"{len(names)} tools published: {names}")
        missing = [n for n in ELASTIC_TOOL_NAMES if n not in names]
        if missing:
            print(f"⚠ contract tools NOT found under their bare names: {missing}")
            print("  → if Agent Builder namespaces ids, map them in _mcp_call().")
        else:
            print("✓ all six contract tool names match")
        out = await live_call("search_events", {"query": "flood", "size": 3})
        print(f"✓ search_events returned {len(out.get('events', []))} contract-shaped "
              f"events (total={out.get('total')})")

    asyncio.run(_probe())

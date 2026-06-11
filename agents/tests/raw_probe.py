"""Dev probe: dump raw MCP envelopes from A's live tools (manual, not pytest).
Used at S1 to pin the adapter to real column names. Bypasses the reshape layer.
"""
import asyncio
import json

from agents import config
from agents.tools import elastic_mcp


async def raw_call(tool: str, args: dict):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(elastic_mcp._mcp_endpoint(),
                                     headers=elastic_mcp._mcp_headers()) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            return result.isError, [getattr(b, "text", None) for b in result.content]


def show(tool: str, args: dict, max_chars: int = 1200):
    is_err, blocks = asyncio.run(raw_call(tool, args))
    print(f"\n=== {tool} (err={is_err}) args={json.dumps(args)[:100]}")
    for b in blocks:
        print((b or "")[:max_chars])


if __name__ == "__main__":
    show("search_events", {"query": "flood Gujarat", "size": 3})
    show("search_events", {"query": "frost", "include_simulated": True, "size": 5}, 800)
    show("match_event_to_suppliers",
         {"event_text": "Severe flooding in Vadodara district, Gujarat — industrial estates "
                        "inundated; production halts at chemical plants in the GIDC estates."},
         1200)
    show("traverse_supply_graph", {"supplier_ids": ["sup-vadodara-chem"]}, 1200)
    show("lookup_exposure", {"product_ids": ["prd-granola-bar", "prd-sparkling-botanical"]}, 1200)
    show("find_alternate_suppliers",
         {"component_id": "cmp-emulsifier",
          "constraints": {"exclude_supplier_ids": ["sup-vadodara-chem"]}}, 1000)
    show("write_decision", {"doc_json": json.dumps({
        "decision_id": "dec-s1-probe-0001", "run_id": "run-s1-probe", "ts": "2026-06-10T23:59:00Z",
        "agent": "orchestrator", "kind": "other", "summary": "S1 adapter probe write",
        "evidence_event_ids": ["evt-gdacs-flood-guj-20260610"], "simulated": False})}, 800)

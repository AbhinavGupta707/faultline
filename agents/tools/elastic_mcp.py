"""Elastic MCP wiring — McpToolset against {KIBANA_URL}/api/agent_builder/mcp.

Phase 0 stub — Session B implements per impl plan §3.3: the McpToolset + a thin logging
wrapper that publishes every call onto the WS as `tool.call` with elastic:true.
ELASTIC_MODE=mock must route to agents/mocks/elastic_fake.py with identical signatures.
"""

ELASTIC_TOOL_NAMES = [
    "search_events",
    "match_event_to_suppliers",
    "traverse_supply_graph",
    "lookup_exposure",
    "find_alternate_suppliers",
    "write_decision",
]

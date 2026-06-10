# Agent Builder tool definitions (Session A)

One JSON file per tool — `search_events.json`, `match_event_to_suppliers.json`,
`traverse_supply_graph.json`, `lookup_exposure.json`, `find_alternate_suppliers.json`,
`write_decision.json` — exactly as created via `POST kbn:/api/agent_builder/tools`
(prefer parameterized ES|QL tools; `index_search` where hybrid BM25+ELSER is easier).

I/O is FROZEN in `contracts/elastic_tools.md`. Definitions are checked in here so they
are reviewable and re-creatable by `elastic/setup_elastic.py`. Verify through the MCP
endpoint (`{KIBANA_URL}/api/agent_builder/mcp`), not just in Kibana.

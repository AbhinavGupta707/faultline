# Live Elastic tools — consumer notes (for Session B at S1, and Session F)

The six tools are live and MCP-verified (`python3 elastic/verify_tools.py` → 29/29).
Endpoint: `{KIBANA_URL}/api/agent_builder/mcp` (Streamable HTTP, header
`Authorization: ApiKey {ELASTIC_API_KEY}`). The ADK `McpToolset` wiring in
`agents/tools/elastic_mcp.py` connects here; `tool_filter` = the six ids below.

The contract I/O in `contracts/elastic_tools.md` is the **target shape**. Agent Builder
tools return their own envelope, so Session B's thin adapter reshapes real results into
the contract shapes (the fixture-backed mock already returns the ideal shape). Nothing
about the contract changed — this is just the wire format of the live tools.

## Result envelope (all five ES|QL tools)

An MCP `call_tool` result's first content block is text holding:

```
{"results":[
  {"type":"query","data":{"esql":"..."}},
  {"type":"esql_results","data":{"columns":[{"name","type"}...],"values":[[...],...]}}
]}
```

Adapter: parse `content[0].text` → find the `esql_results` block → zip `columns`×each
`values` row into dicts. (See `parse_rows()` in `elastic/verify_tools.py`.)

### Column → contract reshape per tool
- **search_events** → rows are flat `world_event` fields. `location` is split into `lat`/`lon`
  columns (rebuild `{lat,lon}`). `score` added. Simulated events already excluded.
- **match_event_to_suppliers** → flat supplier columns + `score` (normalized 0–1, ≥0.5
  confident) + `semantic_score` (raw ELSER). Reshape to `{supplier:{...}, score,
  signals:{semantic_score}}`. `location` from `lat`/`lon`. NOTE: geo boost is **not**
  implemented (semantic-only); the contract's `lat/lon/radius_km` inputs are optional and
  unused — ELSER alone ranks the directly-hit supplier first.
- **traverse_supply_graph** → one row per path. `supplier_chain_json` is a JSON **string**
  of the ordered `chain_node[]` (root first) — `JSON.parse` it. Other fields map 1:1
  (`route_via` may be null).
- **lookup_exposure** → flat `exposure` rows, 1 per (product, component). `monthly_revenue_usd`
  is denormalized in. Returns ALL components for the products (the contract's optional
  `component_ids` filter is not applied — filter consumer-side if needed).
- **find_alternate_suppliers** → flat supplier columns + `score` (0–1). Only suppliers
  pre-qualified via `alternate_for` are returned, ranked by capacity × lead-time.

## write_decision (workflow tool)
Call with a **single** param: `{"doc_json": "<JSON string of the full decision object>"}`
(i.e. `json.dumps(decision)`). A server-side ingest pipeline (`decision-parse`) parses it
into a typed `decision-log` doc — real `evidence_event_ids` array, `related` object,
`simulated` boolean — with `_id = decision_id` (idempotent). The MCP result is a workflow
execution record; treat `status == "completed"` as the ack.

## Indices / inference
- `semantic_text` fields pinned to managed **`.elser-2-elasticsearch`** (the cluster's
  *default* semantic inference here is Jina, so it is pinned explicitly — not a custom
  endpoint). `world-events.event_semantic` is populated via `copy_to` from
  title/summary/place_name, so producers (Session D) never send it.
- Internal index `supplier-graph-paths` backs traversal (materialized by the seeder).
- Re-provision anytime: `setup_elastic.py` (mappings+pipeline) → `seed_generator.py`
  (data) → `setup_tools.py` (workflow+tools) → `verify_tools.py` (gate).

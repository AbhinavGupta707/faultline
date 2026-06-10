# Contract — Elastic Agent Builder tools (exposed via the Elastic MCP server)

> **FROZEN at `phase0`.** Only Session F amends. Canonical schemas:
> [`schemas/faultline.schema.json`](schemas/faultline.schema.json) (`$defs/<tool>_input` /
> `<tool>_output`). Session A builds the real tools (defs exported to `elastic/tools/*.json`);
> Session B's mock (`agents/mocks/elastic_fake.py`) implements the **same names and I/O**
> from `contracts/fixtures/`. Endpoint: `{KIBANA_URL}/api/agent_builder/mcp`
> (Streamable HTTP, header `Authorization: ApiKey <ELASTIC_API_KEY>` — the key needs
> Kibana Agent Builder privileges).

Conventions: all scores normalized to `[0,1]`; `≥0.5` = confident match. Tools never
return `simulated:true` events unless `include_simulated:true`. Unknown extra fields in
outputs must be ignored by consumers.

---

## 1. `search_events` (Watcher)
Hybrid search over `world-events` (BM25 on title/summary + ELSER on `event_semantic`),
optional time window + geo filter, sorted by relevance × recency.

- **Input** (`$defs/search_events_input`): `query` (req), `from?`, `to?` (ISO date-time),
  `geo? {lat, lon, radius_km}`, `include_simulated? = false`, `size? = 20`
- **Output** (`$defs/search_events_output`): `{ events: world_event[], total? }`
- Golden example: [`fixtures/world_events.json`](fixtures/world_events.json) (array of `world_event`)

## 2. `match_event_to_suppliers` (Tracer)
The signature tool: matches unstructured event text to supplier `profile_semantic`
(hybrid BM25+ELSER), boosted by geo proximity to `location` within `radius_km`.

- **Input** (`$defs/match_event_to_suppliers_input`): `event_text` (req), `event_id?`,
  `lat?`, `lon?`, `radius_km? = 500`, `size? = 10`
- **Output** (`$defs/match_event_to_suppliers_output`):
  `{ matches: [{ supplier: <supplier doc>, score, signals?: {semantic_score, bm25_score, geo_distance_km} }] }`
- Golden example: [`fixtures/supplier_matches.json`](fixtures/supplier_matches.json)

## 3. `traverse_supply_graph` (Tracer)
Walks precomputed `supplier-graph` edges from affected suppliers downstream to finished
products. `supplier_chain` ordered upstream→downstream, root first.

- **Input** (`$defs/traverse_supply_graph_input`): `supplier_ids` (req, ≥1), `max_hops? = 4`
- **Output** (`$defs/traverse_supply_graph_output`):
  `{ paths: [{ root_supplier_id, supplier_chain: chain_node[], component_id, component_name?, product_id, product_name?, hops }] }`
- Golden example: [`fixtures/graph_traversal.json`](fixtures/graph_traversal.json)

## 4. `lookup_exposure` (Assessor, Verifier)
Joins `inventory` (per product×component cover) with `products` (revenue).

- **Input** (`$defs/lookup_exposure_input`): `product_ids` (req, ≥1), `component_ids?`
- **Output** (`$defs/lookup_exposure_output`):
  `{ exposures: [{ product_id, product_name, component_id, days_of_cover, on_hand_units?, daily_consumption_units?, unit?, monthly_revenue_usd }] }`
- Golden example: [`fixtures/exposure_lookup.json`](fixtures/exposure_lookup.json)

## 5. `find_alternate_suppliers` (Resourcer)
Semantic similarity over supplier profiles for a component (`alternate_for` boost),
filtered by constraints, excluding the disrupted supplier(s).

- **Input** (`$defs/find_alternate_suppliers_input`): `component_id` (req),
  `constraints? {max_lead_time_days?, required_certifications?, exclude_supplier_ids?, min_capacity?}`,
  `size? = 5`
- **Output** (`$defs/find_alternate_suppliers_output`):
  `{ alternates: [{ supplier: <supplier doc>, score }] }`
- Golden example: [`fixtures/alternate_search.json`](fixtures/alternate_search.json)

## 6. `write_decision` (all agents, via Orchestrator)
Indexes a decision-log doc. Idempotent on `decision_id`.

- **Input** (`$defs/write_decision_input` = `$defs/decision`): full decision doc incl.
  `evidence_event_ids` (required on every conclusion)
- **Output** (`$defs/write_decision_output`): `{ acknowledged: true, decision_id, index: "decision-log" }`
- Golden example: [`fixtures/decision_log.json`](fixtures/decision_log.json)

---

## Index doc shapes (what Session A seeds / Session D writes)

| index | schema def | golden fixture |
|---|---|---|
| `world-events` | `$defs/world_event` (+ server-side `event_semantic`) | `fixtures/world_events.json` |
| `suppliers` | `$defs/supplier` (+ server-side `profile_semantic` semantic_text) | `fixtures/suppliers.json` |
| `components` | `$defs/component` | `fixtures/components.json` |
| `products` | `$defs/product` | `fixtures/products.json` |
| `bom` | `$defs/bom_edge` | `fixtures/bom.json` |
| `supplier-graph` | `$defs/graph_edge` | `fixtures/supplier_graph.json` |
| `inventory` | `$defs/inventory_item` | `fixtures/inventory.json` |
| `decision-log` | `$defs/decision` | `fixtures/decision_log.json` |

Mappings live in `elastic/mappings/*.json` (Session A). What-if events flow through the
identical pipeline distinguished **only** by `simulated:true`. Session D writes to
`world-events-dev` until sync S1, then flips `ELASTIC_EVENTS_INDEX`.

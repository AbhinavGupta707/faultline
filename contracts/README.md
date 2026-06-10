# contracts/ — FROZEN at `phase0`

The parallelism enabler (parallel plan §2). After the `phase0` tag, **only Session F**
edits anything here, and always contract + schema + fixtures in one commit.

- [`ws_protocol.md`](ws_protocol.md) — WebSocket message contract (`GET /ws`)
- [`elastic_tools.md`](elastic_tools.md) — the six Agent Builder MCP tools + index doc shapes
- [`http_api.md`](http_api.md) — REST surface + voice gateway WS framing
- [`components.md`](components.md) — voice/analytics mount props + depth-agent registry
- [`schemas/faultline.schema.json`](schemas/faultline.schema.json) — canonical machine-readable
  schemas (every payload as a named `$def`); [`schemas/fixture_map.json`](schemas/fixture_map.json)
  maps each fixture to its def
- [`fixtures/`](fixtures/) — golden examples, mutually consistent IDs (Northwind Provisions);
  [`fixtures/ws_replay.jsonl`](fixtures/ws_replay.jsonl) — scripted ~70 s full incident
- `test_fixtures.py` — validates every fixture: `pytest contracts/`

Rules: required fields strict, unknown extra fields ignored. If a contract seems wrong,
report in your branch's STATUS.md and stop — Session F adjudicates; never improvise.

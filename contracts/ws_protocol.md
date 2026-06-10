# Contract — WebSocket protocol (`GET /ws` on the agent runtime)

> **FROZEN at `phase0`.** Only Session F amends this file (+ schemas + fixtures, in one commit).
> Canonical machine-readable schemas: [`schemas/faultline.schema.json`](schemas/faultline.schema.json)
> — def names cited per type below. Golden examples: [`fixtures/`](fixtures/), full scripted run:
> [`fixtures/ws_replay.jsonl`](fixtures/ws_replay.jsonl).
> **Compatibility rule:** required fields are strict; consumers MUST ignore unknown extra fields.

## Transport & envelope

- Endpoint: `GET /ws` (FastAPI WebSocket on the agent runtime; `VITE_WS_URL` / `WS_URL`).
- Wire format: one JSON object per WebSocket text message (newline-delimited JSON in
  `ws_replay.jsonl` — one message per line).
- **Every** message, both directions, carries the envelope (`$defs/ws_envelope`):

| field | type | notes |
|---|---|---|
| `type` | string | message type, below |
| `ts` | ISO-8601 date-time | server clock for s2c, client clock for c2s |
| `run_id` | string \| null | null only before any run exists (boot `status`) |
| `seq` | int, optional | monotonic per connection |
| `dir` | `"s2c"`\|`"c2s"`, optional | **only used inside `ws_replay.jsonl`** to mark scripted client lines; never sent on a real socket |
| `payload` | object | type-specific, below |

## Server → client

| `type` | payload schema (`$defs/…`) | drives |
|---|---|---|
| `plan.update` | `plan_update_msg` — `steps[{id,label,status}]`, `active_step` | Mission Control plan |
| `tool.call` | `tool_call_msg` — `call_id, agent, tool, args_summary, status(start\|ok\|err), elastic, latency_ms?, error?` | tool-call chips (Elastic MCP calls flagged `elastic:true` get the distinct treatment) |
| `agent.emit` | `agent_emit_msg` — `agent, kind, payload` | Action Board, Decision Log, **Map** (all map visuals derive from these semantic events — the backend never sends pixels) |
| `decision.logged` | `decision_logged_msg` — full decision-log doc incl. `evidence_event_ids` | Decision Log |
| `approval.request` | `approval_request_msg` — `approval_id, action_kind, summary, context` | approval gate card |
| `status` | `status_msg` — `mode(live\|simulated), feeds_ok, elastic_ok` | header chips |

### `agent.emit` kinds → payload defs

| `kind` | emitted by | payload def | map effect (derived by C1) |
|---|---|---|---|
| `relevant_events` | Watcher | `relevant_events_payload` | coral ripple rings at event locations |
| `exposure_paths` | Tracer | `exposure_paths_payload` | arcs along `supplier_chain` pulse coral toward the product node |
| `ranked_exposures` | Assessor (re-emitted with `enriched:true` by Enricher) | `ranked_exposures_payload` | product nodes ignite per `status` (coral `at_risk` / amber `watch`) |
| `alternates` | Resourcer | `alternates_payload` | candidate supplier nodes highlight; `recommended_supplier_id` gets the gold scan-pulse |
| `draft_po` | Resourcer | `draft_po_payload` | — (Action Board card) |
| `call_event` | Negotiator / voice_gateway | `call_event_payload` | — (live call panel) |
| `verify_result` | Verifier | `verify_result_payload` | product cools to mint when `status_change.to == "secured"` |
| `brief` | Briefer (Session G) | `brief_payload` | — (Decision Log header download) |

**Canonical plan steps** (ids stable for the whole project; UI keys off them):
`scan` → `trace` → `assess` → `approve` → `resource` → `verify`
(labels: "Scan world events", "Trace exposure paths", "Quantify exposure", "Approval gate",
"Secure alternate supply", "Verify coverage").

**Ordering guarantees:** within a run the server emits in causal order (a `tool.call ok`
follows its `start`; `agent.emit` follows the tool calls that produced it; `plan.update`
marks a step `done` only after its emissions). `tool.call` pairs share `call_id`; fast
calls MAY emit a single `status:"ok"` message with no preceding `start`.

## Client → server

| `type` | payload schema | semantics |
|---|---|---|
| `approval.decision` | `approval_decision_msg` — `approval_id, approved, note?` | resolves a pending `approval.request`; idempotent per `approval_id` (equivalent to `POST /approval`) |
| `whatif.run` | `whatif_run_msg` — `scenario` (`whatif_scenario`) | server writes a synthetic `simulated:true` world-event and starts the identical pipeline (equivalent to `POST /whatif`) |
| `chat` | `chat_msg` — `text` | free-text instruction/question to the Orchestrator |
| `voice.intent` | `voice_intent_msg` — `transcript, intent` (`voice_intent`) | forwarded by the frontend from the voice gateway; `action:"approve"/"reject"` with `approval_id` is processed exactly like `approval.decision` |

## Replay file (`fixtures/ws_replay.jsonl`)

A hand-scripted ~75 s full incident (event → trace → assess → approval → re-source →
negotiation call → verify → secured) with realistic `ts` pacing. `lib/replay.ts` replays
it by sleeping the `ts` deltas between consecutive lines. Lines with `dir:"c2s"`
(the operator's `approval.decision`) are choreography: in replay mode the harness pauses
at `approval.request` until the user clicks Approve (or auto-plays the scripted decision
after the scripted delay), then continues. Every line validates against `$defs/ws_message`.

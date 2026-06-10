# Faultline — Implementation Plan (v2, deadline-aware, agent-executable)

This is the **executable build guide** for Faultline, a supply-chain control-tower agent, targeting the **Google Cloud Rapid Agent Hackathon** (https://rapid-agent.devpost.com/), **Elastic partner track**.

> **⏰ HARD DEADLINE: June 11, 2026, 2:00 PM PT** (= 9:00 PM UTC = June 12, 2:30 AM IST). Judging June 22–Jul 6. This plan is structured as a ~24-hour sprint executed by **parallel agent sessions** — see `faultline_parallel_execution_plan.md` for the workstream map, ownership matrix, and sync schedule. Read that file before starting any work.

## 0. Hackathon compliance box (verified against official rules, 2026-06-10)

| Requirement | Our answer |
|---|---|
| Functional agent powered by **Gemini + Google Cloud Agent Builder** | ADK (Python) multi-agent system on Gemini 3 family models |
| Integrate a **partner MCP server** | Elastic Agent Builder MCP server — load-bearing, calls surfaced in UI |
| **Only** Google Cloud AI + the partner's built-in AI permitted *in the product* | All inference = Gemini (Vertex) + Elastic ELSER. No other AI in the runtime. (Coding assistants used to *build* are dev tools, not product components — keep them out of the deployed runtime entirely.) |
| Agent must **execute multi-step tasks**, not just answer questions | SENSE→ASSESS→PLAN→ACT→VERIFY loop with real actions (PO generation, calls) |
| Hosted project URL | Firebase Hosting (frontend) + Cloud Run (backend) |
| Public repo with **license file visible at top** | `LICENSE` (Apache-2.0) at repo root, pushed to public GitHub |
| ~3-min demo video | Recorded at T-5h; backup video recorded at M0 |
| Team ≤ 4 on Devpost; one representative submits | Confirm Devpost team membership **today**, before build |
| Judging criteria | Technological Implementation · Design (UX/UI) · Potential Impact · Quality of Idea — the living map + visible Elastic MCP calls + voice target all four |

**Naming note:** Google rebranded Vertex AI → *Gemini Enterprise Agent Platform* at Cloud Next 2026; the rules still say "Google Cloud Agent Builder," and ADK + Agent Engine are its components. Use the rules' terminology in the README/video.

---

## 1. Target feature set — the FULL BUILD is the target

Parallel agent sessions change the scope math: **we staff more lanes instead of cutting features.** Everything below ships. The only gate is the demo-clean bar (§13): a feature that isn't demo-clean at freeze gets its UI affordance *hidden for the video* — it is never "cut" from the build.

**CORE LOOP (the M0 fallback line — first to go end-to-end):**
1. **Live control loop** — `SENSE → ASSESS → PLAN → ACT → VERIFY` over live world feeds.
2. **Multi-tier exposure tracing** — semantic event→supplier matching, Tier-1→2→3 traversal to finished products.
3. **Quantified exposure** — severity, days-of-cover, $ at risk, ranked.
4. **Autonomous re-sourcing** — discover + qualify alternates, draft contingent POs (PDF → GCS).
5. **Living map** — the signature: disruptions ripple through a glowing supplier graph; products ignite coral, cool to mint when re-sourced.
6. **Decision log** — every conclusion linked to live evidence (`evidence_event_ids`).
7. **Human-in-the-loop** — analysis autonomous; writes/irreversible actions gated by approval.
8. **What-if stress-test mode** — guaranteed demo path independent of the live news cycle.

**FULL BUILD (default expectation — each has a dedicated parallel lane, see parallel plan §3):**
9. **Voice IN** (talk to the tower + voice approval) and **Voice OUT** (in-app negotiation call with live transcript) — Session E.
10. **Executive situation report** — cited, downloadable brief (Briefer) — Session G.
11. **Multimodal enrichment** — Gemini reads recall PDFs / disaster imagery to refine severity — Session G.
12. **BigQuery analytics** — historical risk view: decision-log + exposures streamed to BigQuery, Analytics panel in the UI — Session G.
13. **Second vertical profile** — `company_profile.pharma.json` proving the platform is config-driven (one-line swap, shown for 10 seconds in the video = instant "this is a platform, not a demo" credibility) — Session G.
14. **Agent Engine deployment** alongside the Cloud Run runtime (README + architecture diagram show both) — Session F.

**Optional flourish (only if a lane goes idle):** telephony bridge so the negotiation call rings a real phone (transport only — the AI stays Google).

---

## 2. Repository structure (monorepo, ownership-partitioned)

Directory layout doubles as the **parallel-session ownership map** (one writer per top-level area — see parallel plan):

```
faultline/
├── contracts/                   # ★ FROZEN after Phase 0 — the parallelism enabler
│   ├── ws_protocol.md           # WebSocket message contract (§11.1)
│   ├── elastic_tools.md         # tool names + I/O JSON schemas (§3.3)
│   ├── http_api.md              # REST surface (what-if, approval, report download)
│   └── fixtures/                # golden sample payloads for every contract
│       ├── world_events.json  exposure_paths.json  ranked_exposures.json
│       ├── alternates.json  draft_po.json  call_transcript.json  brief.md
│       └── ws_replay.jsonl      # scripted full-run event stream (frontend dev fuel)
├── agents/                      # ADK multi-agent system (Python)  [Session B]
│   ├── orchestrator.py  watcher.py  tracer.py  assessor.py
│   ├── resourcer.py  negotiator.py  verifier.py
│   ├── depth/                   # [Session G] briefer.py, enrich.py (multimodal), bq_export.py
│   │                            #   plugs into B via the optional-agent registry (§6)
│   ├── tools/                   # elastic_mcp.py (McpToolset wiring), po.py, voice.py
│   ├── prompts/                 # system instructions per agent (one file each)
│   ├── mocks/                   # fixture-backed fake Elastic tools (pre-S1 dev)
│   └── main.py                  # FastAPI app: ADK Runner + WebSocket bridge
├── elastic/                     # index mappings + Agent Builder tool defs  [Session A]
│   ├── mappings/*.json  tools/*.json  setup_elastic.py
├── data/                        #                                            [Session A]
│   ├── seed_generator.py  company_profile.json  company_profile.pharma.json
├── services/                    # Cloud Run FastAPI services
│   ├── feed_ingest/             # [Session D] GDELT/USGS/GDACS/FDA/NOAA → Elastic
│   ├── po_generator/            # [Session D] PO PDF → GCS (or fold into agents/tools)
│   └── voice_gateway/           # [Session E] Gemini Live; voice in & out
├── web/                         # React + Vite frontend          [Sessions C1 + C2]
│   └── src/
│       ├── App shell, routing, theme        # [C1]
│       ├── panels/  Map/                    # [C1 — the hero]
│       ├── panels/  MissionControl/ ActionBoard/ DecisionLog/ WhatIf/   # [C2]
│       ├── features/voice/      # [Session E owns internals; C1 owns the mount point]
│       ├── features/analytics/  # [Session G owns internals; C1 owns the mount point]
│       ├── lib/  ws.ts  api.ts  replay.ts   # [C1]   map/ (deck.gl layers) [C1]
│       └── theme/  tokens.css               # [C1]
├── infra/  setup.sh  env.example  deploy.sh                                 [Session F]
├── README.md   LICENSE (Apache-2.0)   architecture.png
```

Changes vs v1: added `contracts/` (new — see §11), `elastic/` (tool/mapping definitions live in-repo, not only in the cluster), `agents/mocks/`, `agents/depth/` + `web/src/features/{voice,analytics}/` (isolation boundaries so depth features are separate parallel lanes), dropped `services/geocode` (call the Maps Geocoding REST API directly from `feed_ingest`/seed script — a dedicated service is pure overhead).

---

## 3. Elastic — the load-bearing brain

### 3.1 Deployment (do this in the first hour — it has lead time)
- Create an **Elastic Cloud** deployment (Elasticsearch + Kibana, latest 9.x). Serverless also works and is faster to provision.
- ELSER: with `semantic_text` fields, Elastic Cloud auto-uses the managed default inference endpoint **`.elser-2-elasticsearch`** — no manual model download needed. Use the default; don't create a custom inference id.
- Create an API key **with Kibana Agent Builder privileges** (`feature_agentBuilder.read`, `feature_actions.read` on the Kibana application) — a plain ES-only key will 403 on the MCP endpoint. Store endpoint + key in GCP Secret Manager.
- Enable Agent Builder in Kibana if behind a feature flag (Stack Management → check `xpack.onechat`/Agent Builder settings on current version).

### 3.2 Indices & mappings

`world-events` (live, ingested):
```json
{ "id":"keyword","source":"keyword","title":"text","summary":"text",
  "event_type":"keyword","location":{"type":"geo_point"},"place_name":"text",
  "region":"keyword","severity_raw":"float","published_at":"date","url":"keyword",
  "simulated":"boolean",
  "event_semantic":{"type":"semantic_text"} }
```
`suppliers` (seeded):
```json
{ "supplier_id":"keyword","name":"text","tier":"integer",
  "location":{"type":"geo_point"},"country":"keyword","region":"keyword",
  "components":["keyword"],"alternate_for":["keyword"],
  "certifications":["keyword"],"lead_time_days":"integer","capacity":"keyword",
  "profile_semantic":{"type":"semantic_text"} }
```
Plus: `components`, `products`, `bom` (multi-tier edges), `supplier-graph` (precomputed hop edges), `inventory` (`days_of_cover`), `decision-log` (agent-written; every doc carries `evidence_event_ids`). All mappings checked into `elastic/mappings/` and applied by `elastic/setup_elastic.py` (idempotent).

Note `simulated:true` flag on `world-events` — what-if scenarios flow through the *identical* pipeline and indices, distinguished only by this flag (and filtered out of "live" queries).

### 3.3 Agent Builder tools → exposed via the Elastic MCP server

Build these in **Agent Builder** (Kibana UI or `POST kbn:/api/agent_builder/tools`), mostly as parameterized **ES|QL tools**; use the `index_search` tool type where hybrid semantic retrieval is easier that way. Definitions checked into `elastic/tools/*.json` so they're reviewable and re-creatable by script. They are then **automatically exposed** at the MCP endpoint:

```
{KIBANA_URL}/api/agent_builder/mcp        (Streamable HTTP; Authorization: ApiKey …)
```

| Tool | Input | Output | Used by |
|---|---|---|---|
| `search_events` | query, time window, geo (optional) | ranked events | Watcher |
| `match_event_to_suppliers` | event text + geo radius | suppliers ranked by hybrid BM25+ELSER relevance | Tracer |
| `traverse_supply_graph` | supplier_id(s) | affected components → finished products, with hop chain | Tracer |
| `lookup_exposure` | product_ids | inventory, days_of_cover, monthly_revenue | Assessor |
| `find_alternate_suppliers` | component_id + constraints | qualified alternates by semantic similarity | Resourcer |
| `write_decision` | structured log entry | ack | all (via Orchestrator) |

Exact I/O JSON schemas live in `contracts/elastic_tools.md` and are **frozen at Phase 0** so the agent session can build against fixture-backed mocks before the real tools exist.

ADK side — connect with the built-in MCP toolset (no custom client needed; keep `tools/elastic_mcp.py` to just this wiring + a thin logging wrapper that publishes every call to the WebSocket so the UI can prove "Elastic is the brain"):

```python
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

elastic = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=f"{KIBANA_URL}/api/agent_builder/mcp",
        headers={"Authorization": f"ApiKey {ELASTIC_API_KEY}"},
    ),
    tool_filter=["search_events", "match_event_to_suppliers",
                 "traverse_supply_graph", "lookup_exposure",
                 "find_alternate_suppliers", "write_decision"],
)
```
(Verify the exact import paths against the installed `google-adk` version at build time; the toolset + streamable-HTTP connection is the stable pattern.)

> Load-bearing rationale for judges: the agent's core skill is fusing a messy real-time firehose and **semantically** matching unstructured event text to structured supplier records, then traversing relationships. Remove Elastic → no fusion, no fuzzy matching, no graph → no agent.

---

## 4. Seed data (the demo company)

Realistic mid-market **food & beverage** brand — *"Northwind Provisions"* — three product lines (cold-brew coffee cans, granola bars, sparkling botanical drinks). Multi-tier supplier graph with **≥3 guaranteed-disruptable chains**, suppliers at **real lat/lon in event-prone regions** so live feeds genuinely hit:

- **Specialty emulsifier** ← single Tier-3 chemical plant, flood/industrial-fire-prone region (Gujarat, IN) → 2 Tier-1 blenders → 2 SKUs.
- **Coffee beans** ← frost/drought belt farms (Minas Gerais, BR) → Tier-1 roaster → cold-brew line.
- **Aluminium cans** ← rolling mill ← smelter, routed through a strike/weather-exposed **port** → cold-brew + sparkling lines.
- **PET resin / packaging film** ← petrochemical plant, hurricane-exposed (US Gulf Coast).

`seed_generator.py` is **deterministic** (fixed seed) and config-driven from `company_profile.json`; writes suppliers, components, products, BOM, inventory (intentionally tight days-of-cover on emulsifier + coffee chains), and precomputes `supplier-graph` edges. It must also **emit `contracts/fixtures/` samples** so fixtures and seed data never drift.

---

## 5. Google Cloud setup

**Enable APIs (first hour, scripted in `infra/setup.sh`):** Vertex AI, Agent Engine, Cloud Run, Cloud Build, Secret Manager, Maps Platform (Maps JS + Geocoding), Cloud Storage, **BigQuery**, Cloud Scheduler, Firebase Hosting, Cloud TTS/STT (voice fallback path).

**Models (verified current as of 2026-06-10; confirm exact IDs in Model Garden at kickoff):**
- Orchestrator + deep-reasoning steps (Tracer/Assessor): **`gemini-3.1-pro`** (the top reasoning model, 1M context, preview; use `thinking_level` to balance latency).
- Everything else — Watcher triage, Resourcer, Negotiator scripting, Briefer, enrichment, voice intent parsing: **`gemini-3.5-flash`** (GA since Google I/O, 2026-05-19 — near-Pro intelligence at Flash speed, explicitly built for *parallel agentic execution*; quote that in the video).
- Voice (in/out): **`gemini-3.1-flash-live-preview`** — the newest Live native-audio model (post-I/O). Fallback: **`gemini-live-2.5-flash-native-audio`** (GA on Vertex). Session E's first-hour spike decides which; both are permitted Google Cloud APIs alongside the Gemini-3-powered agent.

**Service accounts:** one SA for the agent runtime, one for tool/ingest services; secrets in Secret Manager; least-privilege IAM.

**Deploy targets & the WebSocket decision:** Agent Engine is the managed runtime, but our UI depends on a **server→browser WebSocket stream of every plan step and tool call**, which is most reliably owned by our own server. **Decision: run the ADK `Runner` inside FastAPI on Cloud Run** (supports WS natively, deploys in minutes, still 100% Agent Builder/ADK). If time remains at T-8h, *additionally* deploy the agent to Agent Engine and note it in the README — nice-to-have, not the demo path. Frontend → Firebase Hosting.

---

## 6. Agent layer (ADK)

**Topology:** Orchestrator (`LlmAgent`, gemini-3.1-pro) owns the plan and approval routing; analysis runs as a sequential pipeline; action agents gate on approval.

```
Orchestrator (LlmAgent, owns plan + approval)
├── Watcher  → search_events + Gemini triage of feed batch
├── Tracer   → match_event_to_suppliers + traverse_supply_graph
├── Assessor → lookup_exposure + score severity / days-of-cover / $-at-risk
│      ── [emit ranked exposures to UI; analysis is autonomous] ──
├── (HUMAN APPROVAL GATE — WebSocket approval.request / approval.decision)
├── Resourcer  → find_alternate_suppliers + draft contingent PO
├── Negotiator → call script + in-app voice call (gated)        [Session E]
├── Verifier   → confirm alternate lead-time beats runway; residual risk
└── depth/ (optional-agent registry)                            [Session G]
    ├── Briefer  → executive situation report (cited)
    ├── Enricher → multimodal severity refinement (recall PDFs, imagery)
    └── BQExport → stream run results + decisions to BigQuery
```

Per-agent contracts (each emits structured JSON **matching `contracts/` schemas** and writes to `decision-log` with `evidence_event_ids`):

- **Watcher** — in: feed batch; out: `relevant_events[]` (why-relevant + supplier hints).
- **Tracer** — in: `event`; out: `exposure_paths[]` (event → supplier → component → product, full hop chain).
- **Assessor** — in: `exposure_paths[]`; out: `ranked_exposures[]` (`product, days_of_cover, dollars_at_risk, severity, root_cause_event_id`).
- **Resourcer** — in: `exposure`; out: `alternates[]` + `draft_po`.
- **Negotiator** — in: `alternate`+`draft_po`; out: `call_script`, `call_result`.
- **Verifier** — in: `exposure`+`chosen_alternate`; out: `gap_closed: bool`, `residual_risk`.
- **Briefer** — in: full run state; out: `situation_report.md/pdf` → GCS.

**Implementation notes for the build agent:**
- Use ADK structured output (`output_schema` with Pydantic models generated from the contract schemas) so emissions validate at the boundary instead of via prompt hope.
- `main.py`: FastAPI app exposing `GET /ws` (event stream per §11.1), `POST /whatif`, `POST /approval`, `GET /health`. A callback/plugin on the Runner publishes **every** agent step and tool call (Elastic MCP calls flagged `elastic:true`) onto the WS.
- **Mock-first:** until sync point S1, run against `agents/mocks/elastic_fake.py` (fixture-backed, same tool names/signatures). Switching to live Elastic is a single env var (`ELASTIC_MODE=live`).
- **Optional-agent registry (the B↔G boundary):** `orchestrator.py` discovers depth agents via a tiny registry — `agents/depth/__init__.py` exports `DEPTH_AGENTS: list[LlmAgent]` (empty at Phase 0). Session G fills the list; Session B never edits `depth/`, G never edits anything else in `agents/`. The registry interface (each depth agent's input state keys + emit `kind`) is specified in `contracts/` at Phase 0.
- The control loop ticks via an asyncio task polling `world-events` for new docs (every 30–60s), plus on-demand triggers (what-if, user chat).

---

## 7. Voice subsystem (in + out) — all Google AI  [Session E, fully independent lane]

**Voice OUT (agent → supplier negotiation/confirmation):**
- Negotiator drafts script with Gemini 3 (goal, constraints, fallback positions).
- `voice_gateway` runs the call via **Gemini Live API** (`gemini-3.1-flash-live-preview`; fallback `gemini-live-2.5-flash-native-audio`) as an **in-app web call** (browser audio; supplier side is role-played by the Live model with a "supplier persona" system prompt for the demo — disclose this in the video). Live transcript streamed to the UI over the same WS protocol (`call_event` messages). Always self-identifies as an AI; commitments gated by approval.

**Voice IN (user → control tower):**
- Push-to-talk in the UI streams mic audio → `voice_gateway` → Live API → intent JSON → forwarded to the Orchestrator as a chat/approval action.
- Commands: queries ("what's my biggest risk right now?", "show the coffee chain") and **voice approval** ("approve the re-source for the cold-brew line").

If Live API audio quality/latency disappoints in the in-app context, fallback: Cloud STT → Gemini 3 text → Cloud TTS. Decide at the first-hour spike (go/no-go reported to F by T-12h); don't carry both paths to the end.

**Optional flourish (idle-lane only):** bridge the negotiation call to a real phone via a telephony transport (e.g. SIP/Twilio media stream as *transport only* — all AI remains Google). Attempt only after the in-app call is demo-clean.

---

## 8. Frontend (React + Vite + deck.gl)

**Design tokens** (`theme/tokens.css`) — per `faultline_ui_design_prompts.md`: midnight-nautical base, teal graph edges, amber agent signal, coral/amber/mint risk semantics, technical grotesque + humanist mono. **The living map is the one bold signature; everything else stays quiet and data-dense.**

**Panels:**
1. **Map (hero)** — deck.gl over a dark basemap: supplier nodes, glowing **ArcLayer** edges, expanding **ripple** rings at disruptions, products igniting coral → cooling mint, gold scan-pulse on agent focus. *Basemap decision:* deck.gl over **Google Maps vector (dark styled)** via `@deck.gl/google-maps` to keep the stack all-Google; if the interleaved renderer fights us in the first 2 hours, fall back to a plain dark `TileLayer` — the look is what matters.
2. **Mission Control** — goal, live plan steps, **streaming tool-call chips (Elastic MCP calls visually distinct)**, evidence, confidence, approval gate.
3. **Action Board** — ranked exposures (product · days cover · $ at risk), recommended action, contingent PO drafts, live call status/transcript, verify results.
4. **Decision Log** — timestamped narrative; every conclusion links to source `world-events`.
5. **What-If console** — scenario form + presets; results carry a distinct amber "SIMULATED" treatment.
6. **Voice overlay** — mounts `features/voice` (Session E's component) behind a fixed props interface; renders a disabled mic affordance until E delivers.

**Mock-first (the key to parallelism):** the frontend is built **entirely against `contracts/fixtures/ws_replay.jsonl`** via `lib/replay.ts`, which replays a scripted full incident (event lands → trace → assess → approval → re-source → verify) with realistic pacing. Swapping to the live socket is one env var. The replay file also powers a `?demo=replay` mode kept forever — a deterministic rehearsal/screenshot path and a safety net during the live demo recording.

**Quality floor:** responsive at 1440/1080, keyboard focus, `prefers-reduced-motion` respected.

---

## 9. What-if mode

Console where the user defines `{event_type, location, duration, magnitude}` or picks a preset ("Suez closes 3 weeks", "frost in Minas Gerais"). `POST /whatif` → Orchestrator writes a synthetic `world-events` doc (`simulated:true`) and runs the identical pipeline; UI renders results with the simulated treatment. **This is the guaranteed demo path** — script the video around a preset, with live mode as the opener.

---

## 9b. Analytics — BigQuery historical risk view  [Session G]

- `agents/depth/bq_export.py`: streaming inserts of every completed run (`ranked_exposures`, decisions, outcomes, timings) into BigQuery tables `faultline.runs`, `faultline.exposures`, `faultline.decisions`. Schema mirrors the contract schemas — no translation layer.
- Backfill script generates ~60 days of plausible historical runs from seed data so the analytics view is rich on camera (clearly labeled "historical backfill" in the README — same honesty standard as the feeds).
- `web/src/features/analytics/`: an Analytics panel — risk-over-time sparkline per product line, top recurring chokepoints, $-at-risk-avoided counter. Served by a thin `GET /analytics/summary` endpoint (queries BQ, 60s cache) defined in `contracts/http_api.md`.
- Demo beat: "the control tower also learns — here's 60 days of risk history and the chokepoints it keeps flagging."

---

## 10. Live data sources (free, real-time → not cached)

`feed_ingest` (Cloud Run + Cloud Scheduler every 5 min) normalizes → bulk-writes `world-events` (semantic field populated on ingest by the `semantic_text` mapping). Per-feed notes for the build agent:

- **USGS** — `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson` (GeoJSON, trivial). Start here; it's the 20-minute win.
- **NOAA/NWS** — `https://api.weather.gov/alerts/active` (GeoJSON, needs a User-Agent header).
- **GDACS** — `https://www.gdacs.org/xml/rss.xml` (RSS/XML).
- **openFDA recalls** — `https://api.fda.gov/food/enforcement.json?search=report_date:[...]` (JSON; no key needed at low volume).
- **GDELT 2.0 Doc API** — `https://api.gdeltproject.org/api/v2/doc/doc?query=...&format=json` (highest value, messiest; do last; dedupe on URL).

Events are live; the supplier graph is seeded; matching/traversal are real. **State this on camera as the honesty guarantee.**

---

## 11. Contracts (NEW — frozen at Phase 0; only Session F may amend, by editing the contract file first)

### 11.1 WebSocket protocol (`contracts/ws_protocol.md`)

Server→client messages (newline-delimited JSON; every message has `ts`, `run_id`):

| `type` | payload | drives |
|---|---|---|
| `plan.update` | `steps[{id,label,status}]`, `active_step` | Mission Control plan |
| `tool.call` | `agent, tool, args_summary, status(start/ok/err), elastic:bool, latency_ms` | tool-call chips |
| `agent.emit` | `agent, kind(relevant_events\|exposure_paths\|ranked_exposures\|alternates\|draft_po\|call_event\|verify_result\|brief), payload` | Action Board, Decision Log, **Map** (frontend derives all map visuals from these semantic events — backend never sends pixels) |
| `decision.logged` | decision-log doc incl. `evidence_event_ids` | Decision Log |
| `approval.request` | `approval_id, action_kind, summary, context` | approval gate card |
| `status` | `mode(live\|simulated), feeds_ok, elastic_ok` | header chips |

Client→server: `approval.decision {approval_id, approved, note}` · `whatif.run {scenario}` · `chat {text}` · `voice.intent {transcript, intent}` (from voice gateway via frontend).

### 11.2 Other contracts
- `contracts/elastic_tools.md` — exact input/output JSON schema per §3.3 tool (field names, types, example docs).
- `contracts/http_api.md` — `POST /whatif`, `POST /approval`, `GET /report/{run_id}`, `GET /analytics/summary`, `GET /health`; voice gateway WS endpoint + audio framing.
- `contracts/components.md` — frontend isolation-boundary props: `features/voice` (`{wsUrl, onIntent, disabled}`) and `features/analytics` (`{apiBase}`); plus the depth-agent registry interface (`DEPTH_AGENTS`, each agent's input state keys + emitted `kind`).
- `contracts/fixtures/` — one golden example per schema, **plus `ws_replay.jsonl`** (~60–90s scripted full run). Generated/validated by `seed_generator.py` so data is mutually consistent (same supplier ids everywhere).

**Why this section exists:** five sessions build simultaneously against these files instead of against each other. Any schema change after Phase 0 must be made *in the contract file first* by the integration session (F), then propagated — never improvised inside one component.

---

## 12. Milestone sequence → hour-budgeted (see parallel plan for per-session detail)

> T = deadline (June 11, 2:00 PM PT). M0 remains the fallback line: complete, submittable, competitive.

- **Phase 0 (kickoff, ~90 min, single session):** provision Elastic Cloud + GCP (lead-time items first), `git init` + scaffold, write all `contracts/` + fixtures + `ws_replay.jsonl`, stub every directory so each session starts on green. → spawn all eight parallel sessions.
- **M0 (by T-16h):** seeded Elastic + ELSER + core tools via MCP · Orchestrator+Watcher+Tracer+Assessor live on Gemini 3 · `feed_ingest` with USGS+FDA · UI with living map + ranked exposure + decision log + approval gate, on live WS · deployed · **record backup video.** (Meanwhile the E and G lanes have been building the whole time — M0 is a checkpoint of the core lanes, not a pause for the others.)
- **M1 (by T-10h):** Resourcer (PO → GCS) · Verifier · what-if console · all five feeds · full map ripple/arc/scan animation pass · BigQuery export flowing + backfill loaded.
- **M2 (by T-6h):** Voice IN + OUT mounted · Briefer situation report · multimodal recall-PDF enrichment · Analytics panel · pharma profile swap verified · Agent Engine secondary deployment.
- **M3 (T-6h → T-1h):** *Feature freeze at T-6h — anything not demo-clean is hidden, not patched on camera.* Integration hardening, design pass, README + architecture diagram, **final video by T-3h, Devpost submitted by T-1h.** Submit early; Devpost allows edits until the deadline.

---

## 13. Demo guarantee & risk control

- Suppliers seeded in frequently-active regions so live events hit; what-if preset as the guaranteed path; keep one freshly-pulled real event as fallback; `?demo=replay` mode as the last-resort recording path.
- Elastic MCP calls visibly labeled in Mission Control — the partner integration must be unmistakable in the video's first minute.
- Hard-stop rule: if a stretch feature isn't demo-clean at its cut line, remove its UI affordance entirely (no dead buttons on camera).

---

## 14. Config & secrets (`infra/env.example`)

`GCP_PROJECT` · `VERTEX_LOCATION` · `GEMINI_MODEL_PRO=gemini-3.1-pro` · `GEMINI_MODEL_FLASH=gemini-3.5-flash` · `GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview` · `KIBANA_URL` · `ELASTIC_API_KEY` (Secret Manager) · `ELASTIC_MODE=mock|live` · `MAPS_API_KEY` · `GCS_BUCKET` · `BQ_DATASET=faultline` · `COMPANY_PROFILE=company_profile.json` · `WS_URL` · `VITE_*` mirrors for the frontend. Least-privilege SAs. Never commit keys; verify with a pre-push grep before the repo goes public.

---

## 15. Testing (deadline-realistic)

- **Golden-path test (the one that matters):** scripted event fixture → full pipeline → assert ranked exposure values + decision-log citations. Runs in mock mode (no cloud deps) so every session can run it.
- Unit: each Elastic tool against seed data (golden event→exposure cases) — Session A.
- Contract validation: every fixture validates against its JSON schema in CI (a 10-line pytest).
- Demo dry-run ×2 at T-5h: live mode + what-if, timed to 3 minutes.

---

## 16. Submission checklist (owner: Session F / human rep)

- [ ] Devpost team (≤4) confirmed **before build starts**
- [ ] Public GitHub repo, `LICENSE` (Apache-2.0) at root, visible in About panel
- [ ] Hosted URL live (Firebase + Cloud Run) and tested from a clean browser
- [ ] ~3-min video: live event opener → trace/assess on the map → approval → re-source + verify → (voice if shipped) → Elastic MCP visibly load-bearing → honesty statement
- [ ] Architecture diagram (`architecture.png`) in repo + Devpost
- [ ] Devpost form: Elastic track selected, all fields, video link, repo link, hosted URL
- [ ] Submitted by **T-1h (1:00 PM PT)** — do not ride the deadline

---

*Note: v1 referenced a `faultline_product_spec.md` companion that is not present in this folder — this v2 is self-contained and does not depend on it.*

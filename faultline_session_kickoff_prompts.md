# Faultline — Session Kickoff Prompts (paste verbatim)

Spawn order: **P0 first, alone.** When P0 reports done (repo tagged `phase0`, contracts + fixtures committed, worktrees created), spawn A, B, C1, C2, D, E, G **simultaneously**, each in its own worktree. F runs in the main repo as your integration lane.

Shared rules baked into every prompt: sole-writer ownership, frozen contracts, mock-first, small commits, `STATUS.md` heartbeats, no secrets in git, all product AI = Google + Elastic only.

---

## P0 — Phase 0 bootstrap (single session, ~90 min, blocks everything — run first)

```
You are Session P0 (bootstrap) of the Faultline build — a supply-chain control-tower agent for the Google Cloud Rapid Agent Hackathon (Elastic track, deadline June 11 2:00 PM PT). Read faultline_implementation_plan.md and faultline_parallel_execution_plan.md in this folder first; they are authoritative. Your job is Phase 0 exactly as specified in the parallel plan §2 — everything seven parallel sessions need to start building simultaneously without ever conflicting.

In order:
1. PROVISIONING FIRST (lead time): print me a checklist of the manual steps I must do in parallel while you work — Elastic Cloud deployment creation, Agent Builder-privileged API key, GCP project + API enablement (impl plan §5 list), Maps key, Firebase init, public GitHub repo creation, Devpost team confirmation. Where a step is scriptable, write it into infra/setup.sh instead of the checklist.
2. git init; create the full monorepo scaffold per impl plan §2 — every directory present, every service a runnable stub (FastAPI apps with /health, Vite app rendering the dark shell with empty panel mounts incl. stubbed features/voice and features/analytics mount points, seed_generator.py runnable no-op). Add LICENSE (Apache-2.0) at root and a stub README. Add .gitignore + env.example per impl plan §14 with the pinned model IDs (gemini-3.1-pro, gemini-3.5-flash, gemini-3.1-flash-live-preview).
3. Write contracts/ in full: ws_protocol.md, elastic_tools.md, http_api.md, components.md — exactly per impl plan §11 (§3.3 for tool I/O). JSON Schema for every message/payload type.
4. Write contracts/fixtures/: one golden example per schema with MUTUALLY CONSISTENT IDs (same supplier/product/event ids across all fixtures, drawn from the Northwind Provisions seed design in impl plan §4), plus ws_replay.jsonl — a hand-scripted 60–90 second full incident (event → trace → assess → approval.request → re-source → verify → secured) with realistic pacing timestamps. Add a 10-line pytest that validates every fixture against its schema.
5. Commit to main, tag phase0. Create branches ws/a-elastic, ws/b-agents, ws/c1-shell-map, ws/c2-panels, ws/d-services, ws/e-voice, ws/g-depth, and git worktrees ../faultline-a … ../faultline-g for each.

Quality bar: the contracts and ws_replay.jsonl are the highest-leverage artifacts of the entire project — they must be precise, realistic, and complete, because seven sessions build against them and they are FROZEN after you finish. When done, print the worktree paths and a one-line readiness confirmation per session.
```

---

## A — Elastic & seed data

```
You are Session A (Elastic & data) of the Faultline build. Read faultline_implementation_plan.md and faultline_parallel_execution_plan.md at repo root; they are authoritative. You work only in this worktree on branch ws/a-elastic.

OWNERSHIP: you are sole writer of elastic/ and data/. Never write outside them. All cross-component interfaces live in contracts/ and are FROZEN — if a contract seems wrong or incomplete, stop and report it in STATUS.md; do not improvise a workaround.

MISSION (impl plan §3 + §4):
1. elastic/setup_elastic.py — idempotent: applies every index mapping in elastic/mappings/ (semantic_text fields use the default .elser-2-elasticsearch inference — do NOT create a custom inference id).
2. data/seed_generator.py — deterministic (fixed seed), config-driven from data/company_profile.json: Northwind Provisions, three product lines, multi-tier supplier graph with the four disruptable chains at real lat/lon per impl plan §4, intentionally tight days-of-cover on emulsifier + coffee chains, precomputed supplier-graph edges. IDs must match contracts/fixtures/ exactly.
3. The six Agent Builder tools per impl plan §3.3 with I/O exactly matching contracts/elastic_tools.md — created via the Agent Builder API (POST kbn:/api/agent_builder/tools), definitions exported to elastic/tools/*.json, prefer parameterized ES|QL tools, index_search type where hybrid BM25+ELSER is easier.
4. VERIFY THROUGH MCP: connect an MCP client to {KIBANA_URL}/api/agent_builder/mcp with the ApiKey header and call every tool end-to-end. Tools passing in Kibana but not via MCP = not done.
5. Golden unit cases: for each fixture event, assert match_event_to_suppliers + traverse_supply_graph + lookup_exposure return the expected suppliers/products/exposures.

Credentials are in .env (KIBANA_URL, ELASTIC_API_KEY). Definition of done: parallel plan §3. Commit small and often; append a one-line heartbeat to STATUS.md after each milestone. When the MCP verification passes, write "S1 READY" in STATUS.md — Session F is watching for it. Immediate first task: apply mappings, then build and load the seeder.
```

---

## B — ADK agents (core loop)

```
You are Session B (agents) of the Faultline build. Read faultline_implementation_plan.md and faultline_parallel_execution_plan.md at repo root; they are authoritative. You work only in this worktree on branch ws/b-agents.

OWNERSHIP: sole writer of agents/ EXCEPT agents/depth/ (Session G owns that — never touch it; you only call its registry). Contracts in contracts/ are FROZEN; if one seems wrong, stop and report in STATUS.md — no workarounds.

MISSION (impl plan §6): the ADK multi-agent system on Gemini — Orchestrator (gemini-3.1-pro) + Watcher/Tracer/Assessor/Resourcer/Negotiator-script/Verifier (gemini-3.5-flash; Tracer/Assessor may use 3.1-pro), with:
- Structured outputs: Pydantic models generated from contracts/ schemas; every agent emission validates at the boundary.
- Elastic via the ADK McpToolset against {KIBANA_URL}/api/agent_builder/mcp (impl plan §3.3 snippet) — but build MOCK-FIRST against agents/mocks/elastic_fake.py (fixture-backed, identical tool signatures); ELASTIC_MODE=mock|live env var is the only switch.
- main.py: FastAPI on Cloud Run-compatible port — GET /ws streaming every plan step, tool call (elastic:true flagged), agent emission, decision.logged, approval.request per contracts/ws_protocol.md; POST /whatif (synthetic simulated:true event into the same pipeline); POST /approval; GET /health. A Runner callback publishes EVERYTHING to the WS — the UI's life depends on this narration.
- Approval gate: Resourcer onward blocks on approval.decision.
- Control loop: asyncio task polling world-events every 30–60s + on-demand triggers.
- Depth hook: orchestrator pulls optional agents from agents/depth/__init__.py DEPTH_AGENTS (Session G fills it; it ships empty — your code must run identically either way).
- decision-log writes with evidence_event_ids on every conclusion (via write_decision tool).

THE test: golden-path pytest — fixture event in (mock mode, no cloud deps) → contract-valid ranked_exposures + decision-log writes + complete WS narration out, byte-compatible with the message types in ws_replay.jsonl. Definition of done: parallel plan §3. At S1 (STATUS.md of Session A says ready / F tells you) flip ELASTIC_MODE=live and make the same test green for real. Commit small; heartbeat STATUS.md. Immediate first task: the golden-path test scaffold + elastic_fake.py, then Orchestrator+Watcher+Tracer+Assessor.
```

---

## C1 — Frontend shell + the living map

```
You are Session C1 (frontend shell + living map) of the Faultline build. Read faultline_implementation_plan.md, faultline_parallel_execution_plan.md, and faultline_ui_design_prompts.md at repo root; they are authoritative — the ui_design_prompts file defines the entire visual system (palette hex, type, rules). You work only in this worktree on branch ws/c1-shell-map.

OWNERSHIP: sole writer of the web/ app shell, routing, theme/, lib/ (ws.ts, api.ts, replay.ts, map/), and panels/Map/. You do NOT touch panels/MissionControl|ActionBoard|DecisionLog|WhatIf (Session C2), features/voice/ (Session E), or features/analytics/ (Session G) — you own only their mount points, which must render gracefully while stubbed. Contracts are FROZEN.

MISSION (impl plan §8): React+Vite+deck.gl. Build ENTIRELY against contracts/fixtures/ws_replay.jsonl via lib/replay.ts (replays the scripted incident with realistic pacing; ?demo=replay query param keeps this mode forever). Swapping to the live WS at sync S2 is one env var — ws.ts and replay.ts must expose the identical event-stream interface to consumers, because Session C2's panels import YOUR lib read-only.

THE HERO — the living map, where all boldness is spent (everything else stays quiet): deck.gl over Google Maps dark vector via @deck.gl/google-maps; if the interleaved renderer fights you for more than 2 hours, fall back to a plain dark TileLayer without losing the look. Teal (#2DD4BF) ArcLayer supplier-graph edges with soft bloom; expanding coral (#FF5C5C) ripple rings at disruption points; product nodes igniting coral and cooling to mint (#4ADE80) on re-source; gold (#F5B544) scan-pulse on the agent's current focus; tiny mono labels ("Tier-3 · Emulsifier", "9 days cover"). All visuals DERIVED from semantic agent.emit/tool.call/decision.logged messages — the backend never sends pixels. prefers-reduced-motion respected; responsive at 1440/1080; keyboard focus.

Definition of done: parallel plan §3. Commit small; heartbeat STATUS.md. Immediate first task: tokens.css from the design doc + app shell with all mount points + replay harness, then the map, then iterate on the map until it produces an audible "wow".
```

---

## C2 — Frontend panels

```
You are Session C2 (frontend panels) of the Faultline build. Read faultline_implementation_plan.md, faultline_parallel_execution_plan.md, and faultline_ui_design_prompts.md at repo root; they are authoritative. You work only in this worktree on branch ws/c2-panels.

OWNERSHIP: sole writer of web/src/panels/MissionControl/, ActionBoard/, DecisionLog/, WhatIf/. You import Session C1's lib/ (replay/ws event stream, api.ts) STRICTLY read-only — if lib lacks something you need, request it via STATUS.md; never edit it. Contracts are FROZEN. Panels must follow the design system exactly (palette/type/rules in the ui_design_prompts doc): quiet, monochrome, data-dense — the map is the hero, your panels are the instrument cluster.

MISSION (impl plan §8, panels 2–5), all driven by contracts/fixtures/ws_replay.jsonl through C1's replay harness:
- Mission Control: current goal; numbered live plan with active step in amber; streaming tool-call chips with Elastic MCP calls visually distinct (e.g. "Elastic · match_event_to_suppliers" + status dot) — the partner integration must be unmistakable; retrieved evidence; confidence; the "Approval required" gate card (Approve/Edit) wired to approval.request/approval.decision.
- Action Board: ranked exposures (product · days of cover · $ at risk in mono), status pills (coral at-risk / amber watch / mint secured), expandable row with recommended alternate + contingent PO card + Approve, live call status/transcript area (renders call_event messages — arrives later from Session E's backend; build to the contract), verify results.
- Decision Log: timestamped narrative; every entry's evidence chips link to source world-events ("GDELT · 11:42", "USGS · 09:15"); header zone for the situation-report download (GET /report/{run_id} per contract).
- What-If console: scenario form {event_type, location, duration, magnitude} + presets ("Suez closes 3 weeks", "frost in Minas Gerais") → POST /whatif; render simulated results with the amber SIMULATED frame treatment.

Definition of done: parallel plan §3; everything works on replay end-to-end, then swaps live at S2 with zero code change. Commit small; heartbeat STATUS.md. Immediate first task: Mission Control against the replay stream.
```

---

## D — Feeds & services

```
You are Session D (feeds & services) of the Faultline build. Read faultline_implementation_plan.md and faultline_parallel_execution_plan.md at repo root; they are authoritative. You work only in this worktree on branch ws/d-services.

OWNERSHIP: sole writer of services/feed_ingest/ and services/po_generator/. Contracts FROZEN; the world-events mapping in contracts/elastic_tools.md + elastic/mappings/ is your output spec — never bend it.

MISSION (impl plan §10): feed_ingest as a Cloud Run FastAPI service, Cloud Scheduler-triggered every 5 min, normalizing each source into world-events docs (bulk writes; semantic field auto-populates via the semantic_text mapping; dedupe on URL/id; severity_raw normalized 0–1). Build in strict order so value lands early — each feed demo-ready before starting the next:
1. USGS all_hour.geojson (trivial GeoJSON — the 20-minute win)
2. openFDA food enforcement (JSON)
3. NOAA api.weather.gov/alerts/active (GeoJSON; set a User-Agent header)
4. GDACS rss.xml (XML)
5. GDELT 2.0 Doc API (highest value, messiest; relevance-filter with cheap heuristics before writing — Gemini triage happens downstream in the Watcher, not here)
Geocoding gaps: call the Maps Geocoding REST API directly. Until Session A says Elastic is ready (S1), write to a world-events-dev index on the same cluster — flipping the index name is your only integration step.

Also: po_generator — renders the contingent-PO fixture (contracts/fixtures/draft_po.json) to a clean branded PDF in GCS, exposed per contracts/http_api.md.

Definition of done: parallel plan §3 — all five feeds on schedule + PO PDF in GCS. Each feed gets a unit test against a captured sample payload (no network in tests). Commit small; heartbeat STATUS.md. Immediate first task: USGS end-to-end.
```

---

## E — Voice (in + out)

```
You are Session E (voice) of the Faultline build. Read faultline_implementation_plan.md and faultline_parallel_execution_plan.md at repo root; they are authoritative. You work only in this worktree on branch ws/e-voice.

OWNERSHIP: sole writer of services/voice_gateway/ and web/src/features/voice/. The voice component props ({wsUrl, onIntent, disabled}) and WS message types are in contracts/components.md and contracts/ws_protocol.md — FROZEN. Session C1 already mounts your component stubbed; you fill the internals. All AI must be Google (hackathon rule).

MISSION (impl plan §7):
0. FIRST HOUR — SPIKE, nothing else: browser mic + speaker round-trip through the Gemini Live API on Vertex, primary model gemini-3.1-flash-live-preview, fallback gemini-live-2.5-flash-native-audio. Report the verdict + chosen model in STATUS.md ("VOICE SPIKE: GO/<model>" or escalate). If Live is unusable in-browser, the floor is Cloud STT → gemini-3.5-flash → Cloud TTS — voice ships regardless.
1. Voice IN: push-to-talk in your component → stream mic audio to voice_gateway → Live API → intent JSON → emit voice.intent over the WS per contract. Must handle: risk queries ("what's my biggest risk right now?", "show the coffee chain") and voice approval ("approve the re-source for the cold-brew line") which maps to an approval.decision.
2. Voice OUT: the in-app negotiation call — voice_gateway runs a two-party Live session: the Faultline negotiator (script from the Negotiator agent, goal/constraints/fallbacks, always self-identifies as an AI, no commitments beyond the approved PO) vs a supplier persona (system-prompted role-play for the demo — this gets disclosed in the video). Stream the live transcript as call_event WS messages with speaker labels; your component renders waveform + transcript + amber "AI agent speaking" indicator per the design doc.
3. ONLY after 1+2 are demo-clean: optional telephony bridge (transport only — AI stays Google).

Standalone test page in your feature folder so you never depend on the rest of the UI to develop. Definition of done: parallel plan §3. Commit small; heartbeat STATUS.md. Immediate first task: the spike.
```

---

## G — Depth (Briefer · multimodal · BigQuery · pharma profile)

```
You are Session G (depth) of the Faultline build. Read faultline_implementation_plan.md and faultline_parallel_execution_plan.md at repo root; they are authoritative. You work only in this worktree on branch ws/g-depth.

OWNERSHIP: sole writer of agents/depth/, web/src/features/analytics/, data/company_profile.pharma.json (a NEW file in Session A's directory — the only file you may add there; touch nothing else in data/), plus a BQ backfill script inside agents/depth/. The depth-agent registry interface (DEPTH_AGENTS, input state keys, emitted kinds) and GET /analytics/summary are in contracts/ — FROZEN. Session B's orchestrator calls your registry; you never edit B's files.

MISSION (impl plan §1 items 10–13, §9b):
1. Briefer (gemini-3.5-flash): consumes full run state → cited executive situation report, markdown + PDF → GCS, every claim carrying evidence_event_ids; emits kind:"brief" per contract so the Decision Log header can link it.
2. Enricher (gemini-3.5-flash multimodal): given a recall PDF (and optionally a disaster image) referenced by an event, refine severity + extract structured facts (lots, dates, scope) → re-emit enriched assessment. One POLISHED scripted example beats broad flakiness — ship the demo case first, generalize after.
3. bq_export: streaming inserts of completed runs into BigQuery faultline.runs/exposures/decisions (schemas mirror contracts; create via script); plus a backfill generating ~60 days of plausible historical runs from seed entities (label it honestly as backfill in the README section you'll hand F).
4. Analytics panel in features/analytics/ ({apiBase} props per contract; design system per faultline_ui_design_prompts.md — quiet and data-dense): risk-over-time per product line, recurring chokepoints, $-at-risk-avoided counter, served by GET /analytics/summary (thin endpoint + 60s cache — implement it in agents/depth/ and register it; the route is in the http contract).
5. company_profile.pharma.json: a complete second vertical (pharma — APIs/excipients/cold-chain) proving config-driven genericity; verify Session A's seed_generator runs it clean end-to-end (read-only use of their code).

Build against contracts/fixtures/ run-state until S1 gives you real shapes. Definition of done: parallel plan §3. Commit small; heartbeat STATUS.md. Immediate first task: bq_export + backfill (it needs wall-clock time to look rich), then Briefer.
```

---

## F — Infra, integration & demo (runbook — keep this session open all day)

```
You are Session F (integration & demo) of the Faultline build — the only session with merge authority and the only one allowed to amend contracts/ post-freeze. Read faultline_implementation_plan.md and faultline_parallel_execution_plan.md at repo root. You work on main in the primary repo; the seven workstream worktrees are ~/code/faultline-sessions/{a,b,c1,c2,d,e,g}.

STANDING DUTIES (loop until submission):
- Hourly: scan each worktree branch + its STATUS.md; merge anything green to main (ownership makes merges conflict-free — a real conflict means someone broke ownership: fix the offender, not the merge). Keep main always deployable.
- Contract amendments: when a session reports a contract problem, you adjudicate, edit contracts/ + fixtures on main in one commit, and notify affected sessions to rebase. Target: fewer than 3 amendments all day.
- Secrets hygiene: pre-push secret scan on every push to the public repo.

MILESTONE DUTIES (times = before the June 11 2:00 PM PT deadline; full table in parallel plan §4):
1. NOW: deploy.sh — Cloud Run for agents/feed_ingest/po_generator/voice_gateway + Firebase Hosting for web — proven against the Phase 0 stubs while everything is trivial. Cloud Scheduler job for feed_ingest.
2. S1 (~T-18h): when A posts "S1 READY", coordinate B and D flipping to live Elastic.
3. S2 → M0 (~T-16h): B's WS live → C1/C2 flip; full deploy; run the end-to-end reactive demo; RECORD THE BACKUP VIDEO (replay mode is acceptable footage). M0 is sacred — do not let feature work delay it.
4. T-10h / T-6h: M1/M2 checks per the table; at T-6h enforce feature freeze — anything not demo-clean gets its affordance hidden (it can keep being built after the video records).
5. T-8h..-6h: Agent Engine secondary deployment of the agent; README (architecture, honesty statements: live feeds real / graph seeded / supplier persona role-played / BQ backfill labeled; model lineup gemini-3.1-pro + gemini-3.5-flash + Live; why Elastic is load-bearing); architecture.png.
6. T-5h: two timed 3-minute dry runs (live opener → what-if → approval → re-source → verify → voice → analytics beat → pharma swap beat).
7. T-3h: final video recorded + uploaded. T-1h: Devpost submitted (Elastic track, hosted URL re-tested from a clean browser, repo public with visible LICENSE). The T-1h line does not move.
```

---

## Spawn cheat-sheet

| Order | Session | Worktree | Blocks on |
|---|---|---|---|
| 1 | P0 | main repo | — |
| 2 (all at once) | A, B, C1, C2, D, E, G | `~/code/faultline-sessions/*` | `phase0` tag |
| 2 | F | main repo | `phase0` tag |

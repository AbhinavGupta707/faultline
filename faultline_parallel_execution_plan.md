# Faultline — Parallel Execution Plan (multi-session agent build)

Companion to `faultline_implementation_plan.md` (v2). This file is the **operating manual for running the build as parallel Claude Code sessions** against the June 11, 2:00 PM PT deadline.

The design principle: **parallelism is bought with contracts, not coordination.** One short serial phase produces frozen interface contracts + golden fixtures; after that, eight workstreams build against the contracts (not against each other), with mocks standing in for every cross-stream dependency until scheduled sync points. No session ever waits on another to write code. The full feature set ships — scope is absorbed by adding lanes, not by cutting.

---

## 1. Why this decomposition is conflict-free

Three mechanisms, all mandatory:

1. **Directory ownership** — every path in the repo has exactly one writing session (§3). Two sessions never edit the same file. The only shared-read area is `contracts/`, which is frozen.
2. **Contract-first interfaces** — every cross-stream boundary (WS protocol, Elastic tool I/O, HTTP API, voice component props) is specified as JSON schema + golden fixture in Phase 0, *before* any feature code. Consumers code against fixtures; producers code toward the same fixtures. Integration is then verification, not negotiation.
3. **Mock-first dependencies** — each stream ships with a fixture-backed mock of everything it consumes (`agents/mocks/elastic_fake.py`, `web/src/lib/replay.ts`, a stub voice panel). Every stream reaches a demonstrable state with zero other streams finished. Flipping mock→live is an env var, not a refactor.

Result: the dependency graph below has edges only at *sync points*, not during build.

```
Phase 0 (serial, ~90 min)
  └─► contracts/ + fixtures/ + scaffold + cloud provisioning kicked off
        │
        ├──► A:  Elastic & seed data ──────┐
        ├──► B:  ADK agents (mocked) ──────┤── S1: B swaps mock→live Elastic
        ├──► C1: Shell + living map ───────┤── S2: C1/C2 swap replay→live WS
        ├──► C2: Panels (replay) ──────────┤
        ├──► D:  Feeds & PO service ───────┤── (writes Elastic per contract; nobody blocks on D)
        ├──► E:  Voice gateway ────────────┤── S3: E's panel mounts into C1's shell
        ├──► G:  Depth (Briefer/BQ/multi-  ┤── S3: depth agents register; analytics panel mounts
        │        modal/pharma profile)     │
        └──► F:  Infra / integration ──────┴── S4: deploy → M0 video → polish → submit
```

---

## 2. Phase 0 — the serialization point (ONE session, ~90 min, highest-leverage work of the project)

Do these in order; cloud provisioning goes first because it has lead time and zero of it depends on code:

1. **Provisioning (fire-and-forget, ~20 min of clicking while the rest proceeds):**
   - Elastic Cloud deployment (or Serverless project) → note `KIBANA_URL`, create Agent Builder-privileged API key.
   - GCP project: enable APIs (impl plan §5), create 2 SAs, Secret Manager entries, GCS bucket, Maps key, Firebase Hosting init.
   - Create the **public GitHub repo now** with `LICENSE` (Apache-2.0) + stub README — license visibility is a submission requirement; don't leave it for the end.
   - Confirm Devpost team (≤4) + Elastic track selection.
2. **`git init` + full scaffold** — every directory from impl plan §2 exists with a runnable stub (FastAPI apps return `/health`, Vite app renders the shell + empty panels, `seed_generator.py` runs no-op). Each session starts on green, not on an empty folder.
3. **Write `contracts/`** — `ws_protocol.md`, `elastic_tools.md`, `http_api.md` exactly per impl plan §11, plus the voice component interface (`features/voice` props: `{wsUrl, onIntent(intent), disabled}`).
4. **Write `contracts/fixtures/`** — golden payloads with **mutually consistent IDs** (same supplier/product ids across all fixtures), and **`ws_replay.jsonl`**: a hand-scripted 60–90s full incident (event → trace → assess → approval.request → re-source → verify → secured). This single file is what lets the frontend session build the entire animated experience alone.
5. **Commit to `main`, tag `phase0`.** Create branches `ws/a-elastic`, `ws/b-agents`, `ws/c1-shell-map`, `ws/c2-panels`, `ws/d-services`, `ws/e-voice`, `ws/g-depth`. Session F stays on `main`.

**Freeze rule:** after the `phase0` tag, only Session F edits `contracts/`. Any session needing a schema change requests it from F; F updates the contract + fixtures on `main`, other sessions rebase. In practice you get ~2 such changes all day if Phase 0 is done carefully.

---

## 3. Workstreams & ownership matrix

| Session | Branch | Owns (sole writer) | Consumes (read-only) | Mock until sync |
|---|---|---|---|---|
| **A — Elastic & data** | `ws/a-elastic` | `elastic/`, `data/` | `contracts/` | — (A is a producer) |
| **B — Agents (core loop)** | `ws/b-agents` | `agents/` *except* `agents/depth/` | `contracts/`, fixtures | `agents/mocks/elastic_fake.py` until S1 |
| **C1 — Shell + living map** | `ws/c1-shell-map` | `web/` shell, routing, `theme/`, `lib/` (`ws.ts`, `api.ts`, `replay.ts`, `map/`), `panels/Map/`, mount points for voice/analytics | `contracts/`, `ws_replay.jsonl` | `lib/replay.ts` until S2 |
| **C2 — Panels** | `ws/c2-panels` | `web/src/panels/{MissionControl,ActionBoard,DecisionLog,WhatIf}/` | `contracts/`, `ws_replay.jsonl`, C1's `lib/` (read-only import) | replay until S2 |
| **D — Feeds & services** | `ws/d-services` | `services/feed_ingest/`, `services/po_generator/` | `contracts/` (world-events schema, PO schema) | writes to a `world-events-dev` index until S1 |
| **E — Voice** | `ws/e-voice` | `services/voice_gateway/`, `web/src/features/voice/` | `contracts/` (voice props + WS types) | standalone test page until S3 |
| **G — Depth (Briefer · multimodal · BigQuery · pharma)** | `ws/g-depth` | `agents/depth/`, `web/src/features/analytics/`, `data/company_profile.pharma.json`, BQ backfill script | `contracts/` (depth registry, analytics API), fixtures | fixture run-state until S1; panel against canned `/analytics/summary` JSON until S3 |
| **F — Infra, integration, demo** | `main` | `infra/`, `contracts/` (post-freeze amendments), `README.md`, `architecture.png`, root configs; **merge authority** | everything | — |

Notes:
- **B and C1/C2 never talk to each other directly** — only through the WS contract. This is the highest-risk boundary; the `ws_replay.jsonl` fixture *is* the integration test for it.
- **C1/C2 boundary:** C1 owns everything shared (shell, lib, theme, map); C2 owns only its four panel folders and imports C1's `lib/` read-only. C1 stubs all four panel mount points at Phase 0 so C2's work drops in without touching shell files.
- **D is fully decoupled**: its only interface is the `world-events` mapping. Nobody blocks on D.
- **E and G are fully decoupled**: own services/modules behind fixed contracts (voice props, depth-agent registry, analytics endpoint), with stubs already mounted at Phase 0. If either slips, the mount point stays hidden — zero blast radius on the core.
- **G's only shared-file exception:** `data/company_profile.pharma.json` lives in A's directory but is a *new file* only G writes — no conflict by construction.
- **F is the only session that merges.** Workstreams commit to their branches continuously; F merges at sync points (and on request). Because of directory ownership, merges are conflict-free by construction — if F ever sees a real conflict, someone broke ownership and that's the bug.
- Humans: with up to 4 teammates, assign roughly A+D / B+G / C1+C2+E / F as babysitting lanes — each person drives ~2 sessions. One person owns F end-to-end including the video.

### Per-session deliverable definitions of done

- **A:** mappings applied; deterministic seed loaded; 6 Agent Builder tools created + returning correct shapes **through the MCP endpoint** (verified with an MCP client, not just Kibana); golden event→exposure unit cases pass; tool defs exported to `elastic/tools/`.
- **B:** golden-path test green in mock mode (scripted event in → contract-valid `ranked_exposures` + decision-log writes + full WS narration out); approval gate round-trip; what-if endpoint; depth-registry hook in orchestrator; then S1 swap green against live Elastic.
- **C1:** app shell + tokens + replay harness; the living map fully alive on replay — teal arcs, coral ripple rings, product ignite/cool transitions, gold scan pulse, node labels; voice/analytics mount points stubbed; reduced-motion + responsive; then S2 swap green.
- **C2:** Mission Control (live plan, Elastic-flagged tool chips, evidence, confidence, approval gate card), Action Board (ranked exposures, PO card, call status), Decision Log (evidence-chip links), What-If console — all driven by replay; then S2 swap green.
- **D:** all five feeds ingesting on schedule with normalized docs (build order USGS → FDA → NOAA → GDACS → GDELT, so value lands early); `po_generator` renders the fixture PO to PDF in GCS.
- **E:** spike Live API in-browser audio **first hour** with `gemini-3.1-flash-live-preview` (fallback `gemini-live-2.5-flash-native-audio`) — report go/model-choice to F; then voice-in intents flowing as `voice.intent` WS messages (incl. voice approval) and the in-app negotiation call with streaming transcript. Telephony bridge only after all of that is demo-clean.
- **G:** Briefer producing a cited situation report (md + PDF → GCS); multimodal Enricher refining severity from a recall PDF (one polished scripted example); `bq_export` streaming runs to BigQuery + 60-day backfill; Analytics panel live on `/analytics/summary`; `company_profile.pharma.json` swap demo verified end-to-end with A's seeder.
- **F:** deploy pipeline (`deploy.sh`: Cloud Run ×N + Firebase) working by S2; M0 backup video; contract amendments; Agent Engine secondary deployment; README + architecture diagram; final video + Devpost submission.

---

## 4. Sync schedule (T = June 11, 2:00 PM PT)

| Time | Sync | What happens | Failure fallback |
|---|---|---|---|
| ~T-22h | **Phase 0 done** | Sessions A–G spawn from `phase0` tag | — |
| T-18h | **S1** | A's Elastic is live + seeded + MCP-verified → B sets `ELASTIC_MODE=live`; D points at real `world-events`; G gets real run-state shapes | B/G keep shipping on mocks; retry in 2h |
| T-16h | **S2 → M0** | B's WS live on Cloud Run → C1/C2 swap replay→live; F deploys all; end-to-end reactive demo; **F records backup video** | C1 demos on replay for the backup video (visually identical) |
| T-12h | **Voice model decision** | E reports Live model choice (3.1-flash-live vs 2.5 native-audio vs STT/TTS pipeline) from its first-hour spike | STT→Gemini→TTS pipeline is the floor — voice still ships |
| T-10h | **M1 check** | Resourcer/Verifier/what-if merged + deployed; all five feeds in; BQ export + backfill flowing | Reorder D's remaining feeds; G prioritizes analytics over Briefer polish |
| T-6h | **Feature freeze (S3)** | Voice + analytics panels mounted; depth agents registered; pharma swap verified; last merge of feature branches | Anything not demo-clean is hidden for the video, finished after recording if time remains |
| T-5h | **Dry runs ×2** | Timed 3-min run-throughs, live + what-if | Fall back to `?demo=replay` for recording |
| T-3h | **Final video done** | Recorded, uploaded, linked | Backup video from S2 |
| T-1h | **SUBMITTED** | Devpost form complete; hosted URL re-tested from clean browser | — (this line does not move) |

Between syncs, F polls each branch roughly hourly, merging anything green to `main` — keep `main` always deployable rather than batching big-bang merges.

---

## 5. Mechanics for running the sessions

- **Worktrees, not clones:** `git worktree add ../faultline-a ws/a-elastic` etc. — one worktree per session, one Claude Code session per worktree. Sessions physically cannot collide on files, and F merges locally with full visibility.
- **Kickoff prompts:** full ready-to-paste prompts for every session (P0, A, B, C1, C2, D, E, G, plus the F runbook) live in **`faultline_session_kickoff_prompts.md`**. Paste verbatim at spawn; each encodes ownership, contracts discipline, definition of done, and the first task.
- **Env discipline:** every session gets `.env` from `infra/env.example` with the *shared* dev project credentials; only F touches production config. Secrets never in git — F runs a pre-push secret scan before every push to the public repo.
- **Status heartbeat:** each session appends a one-liner to its branch's `STATUS.md` (owned per-branch, so no conflicts) after each milestone — F reads these instead of interrupting sessions.

---

## 6. Emergency fallback order (not a plan — a parachute)

**The expectation is zero cuts**: every feature has its own lane, and a slipping lane's blast radius is already contained by the mount-point design (hidden affordance, not broken build). This list exists only so that *if* multiple lanes fail simultaneously near freeze, nobody debates priorities at 4 AM. De-prioritize from the top, and "de-prioritize" means *hide for the video, keep building after recording* — Devpost takes edits until the deadline:

1. Telephony bridge (the in-app call is the demo path anyway)
2. GDELT feed (USGS/NOAA/GDACS/FDA still live)
3. Multimodal recall-PDF moment
4. Pharma profile swap beat
5. Agent Engine secondary deployment
6. Briefer / situation report
7. Analytics panel (keep the BQ export running regardless — it's cheap)
8. Voice OUT (keep Voice IN + voice approval)
— Below this line nothing moves, ever: living map, control loop, Elastic MCP tools, exposure ranking, approval gate, decision log, what-if, deployment, video, submission.

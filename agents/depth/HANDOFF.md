# Depth lane (Session G) — integration handoff for Session F / B

Everything here lives under `agents/depth/` (sole writer: G), plus the Analytics panel in
`web/src/features/analytics/` and `data/company_profile.pharma.json`. The lane runs
**fully offline** for dev/demo and lights up the cloud path when creds are present.

## What ships
| Piece | File | Online path | Offline path (default) |
|---|---|---|---|
| Briefer (cited situation report) | `briefer.py` | report md/pdf → GCS; emits `kind:"brief"` | local `_artifacts/`, dependency-free PDF |
| Multimodal Enricher | `enrich.py` | Gemini-3.5-flash reads recall PDF/image (`ENRICH_LLM=1`) | deterministic regex extraction (scripted Class II recall) |
| BQ export + 60-day backfill | `bq_export.py`, `warehouse.py` | streaming inserts → `faultline.runs/exposures/decisions` | NDJSON `_warehouse/` twin |
| Analytics summary + report routes | `api.py`, `analytics.py` | BQ query, 60 s cache | same query over NDJSON; fixture fallback when empty |
| Analytics panel | `web/src/features/analytics/` | fetches `${apiBase}/analytics/summary` | bundled `analytics_summary.json` fixture |
| Pharma vertical | `data/company_profile.pharma.json` | `COMPANY_PROFILE=company_profile.pharma.json` | seed_generator dry-run verified |

## Wiring into the agent runtime (Session B / F)
1. **HTTP routes** — one line in `agents/main.py`:
   ```python
   import agents.depth as depth
   app.include_router(depth.router)     # GET /analytics/summary, GET /report/{run_id}
   ```
2. **Depth agents** — `agents.depth.DEPTH_AGENTS` is the frozen registry (contracts
   components.md §3). It is populated with ADK `BaseAgent`s when `google.adk` imports.
   The orchestrator iterates it after Verify; each agent reads `ctx.session.state` and
   writes results back:
   - `state["brief"]` ← Briefer's `$defs/brief_payload`
   - `state["ranked_exposures"]` ← Enricher's refined re-emit (`enriched: true`)
   - `state["_emits"]` ← buffered `[{kind, payload}]` for B to replay as ws `agent.emit`
   - `state["_decisions"]` ← `[$defs/decision]` (kinds `brief`, `enrich`) for B to
     `write_decision` + emit as `decision.logged`
   BQExport reads `state["_decisions"]` and streams the run.
3. **Preferred alternative (full WS narration in one call)** — if B would rather drive the
   depth lane directly than through `DEPTH_AGENTS`, call:
   ```python
   agents.depth.run_all_depth(session.state, emit=ws_emit)   # emit(kind, payload)
   ```
   This runs Briefer→Enricher→BQExport, narrating each emission through B's callback, and
   never raises into the core loop (failures are logged and skipped).

## Standalone (before B is ready)
```
uvicorn agents.depth.serve:app --port 8090           # /analytics/summary, /report/{run_id}, /health
python -m agents.depth.bq_export create              # create BQ dataset + tables (or NDJSON)
python -m agents.depth.bq_export backfill --reset     # ~60 days of history (run at deploy time)
python -m agents.depth.bq_export stream              # stream the golden run
python -m agents.depth.briefer                       # print the golden brief + markdown
python -m agents.depth.enrich                        # run the scripted recall enrichment
```
Force a backend with `FAULTLINE_WAREHOUSE=local|bq`; otherwise it auto-selects BQ when
`GCP_PROJECT` is set and the client imports, else local.

## ⚠ Honesty note for the README (same standard as the live feeds)
`bq_export backfill` generates **~60 days of plausible *synthetic* historical runs** from
the seed entities so the Analytics panel is rich on camera. **Every backfilled row carries
`backfill: true`** in `faultline.runs/exposures/decisions`, and the
`/analytics/summary` response sets `includes_backfill: true`. This is clearly-labelled
demo history, **not** real incident data — present it that way in the video and README.
Live/what-if runs streamed during the demo are real and carry `backfill: false`.

## Env
`BQ_DATASET` (default `faultline`), `GCP_PROJECT`, `GCS_BUCKET`, `FAULTLINE_WAREHOUSE`,
`BRIEFER_LLM` / `ENRICH_LLM` (opt-in Gemini paths, off by default),
`GEMINI_MODEL_FLASH` (default `gemini-3.5-flash`). Optional pip deps in
`agents/depth/requirements.txt`.

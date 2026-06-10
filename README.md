# Faultline — Supply-Chain Control Tower Agent

An autonomous supply-chain control tower for the **Google Cloud Rapid Agent Hackathon**
(**Elastic** partner track). Faultline watches live world feeds (earthquakes, storms,
recalls, news), semantically matches disruptions to a multi-tier supplier graph in
**Elasticsearch**, quantifies exposure ($ at risk, days of cover), and — gated by human
approval — re-sources supply autonomously: finds qualified alternates, drafts contingent
POs, confirms by voice call, and verifies the gap is closed. All of it narrated live on
a glowing world map.

> **Status: Phase 0 scaffold.** Contracts are frozen (`contracts/`), every directory is
> a runnable stub, and seven parallel workstreams build from here. See
> `faultline_implementation_plan.md` and `faultline_parallel_execution_plan.md` (authoritative).

## Stack (hackathon-compliant)
- **Agents:** Google Cloud Agent Builder — ADK (Python) multi-agent system on **Gemini 3**
  (`gemini-3.1-pro` orchestration/reasoning, `gemini-3.5-flash` everywhere else,
  `gemini-3.1-flash-live-preview` voice). Runtime on Cloud Run; Agent Engine secondary deploy.
- **Partner MCP:** **Elastic Agent Builder MCP server** — load-bearing: semantic event→supplier
  matching (ELSER), graph traversal, exposure lookup, decision log. Every call surfaced in the UI.
- **Frontend:** React + Vite + deck.gl living map, Firebase Hosting.
- **Data:** live feeds (USGS, NOAA, GDACS, openFDA, GDELT) → Elasticsearch; BigQuery analytics.

## Repo map (one writer per area — see parallel plan §3)
```
contracts/   frozen interfaces + golden fixtures + ws_replay.jsonl   (the parallelism enabler)
agents/      ADK multi-agent system + FastAPI WS bridge              [B, depth/ = G]
elastic/     index mappings + Agent Builder tool definitions         [A]
data/        deterministic seed generator + company profiles         [A]
services/    feed_ingest · po_generator · voice_gateway              [D, E]
web/         React control-tower UI (map hero + panels)              [C1, C2, E, G]
infra/       setup.sh · env.example · deploy.sh · provisioning       [F]
```

## Quickstart (stubs)
```bash
cp infra/env.example .env                     # fill in credentials (never committed)
pip install -r requirements-dev.txt && pytest contracts/   # validate contract fixtures
cd agents && pip install -r requirements.txt && uvicorn main:app --port 8080   # /health, /ws
cd web && npm install && npm run dev          # dark shell on replay fixtures
python3 data/seed_generator.py --dry-run      # deterministic seed (no-op until Session A)
```

## Honesty notes (kept current for judging)
World events are **live** ingested feeds; the demo company ("Northwind Provisions") and its
supplier graph are **seeded**; matching, traversal and scoring are real. What-if scenarios run
the identical pipeline flagged `simulated:true`. The negotiation-call counterparty is a
role-played supplier persona (disclosed in the video). BigQuery history includes a labeled backfill.

## License
Apache-2.0 — see [LICENSE](LICENSE).

# STATUS — per-branch heartbeat (append one line per milestone; owned per-branch, never merged across)

2026-06-10 · P0 · Phase 0 bootstrap in progress.
2026-06-10 · G · bq_export + warehouse (BigQuery + offline NDJSON twin) + 60-day backfill (~40 runs, honest backfill:true) done; analytics summary query + /analytics/summary (60s cache) + /report/{run_id} routes live on serve.py; chokepoint ranking matches fixture (vadodara>ulsan>minas).
2026-06-10 · G · Briefer done — deterministic cited situation report (md + PDF via dependency-free writer → GCS/local), reproduces golden brief.json ($460k averted), emits kind:"brief".
2026-06-10 · G · Enricher done — scripted Class II recall PDF → regex fact extraction (lots/dates/scope) → severity refine + ranked_exposures re-emit (enriched:true), kind:"enrich". Optional Gemini multimodal behind ENRICH_LLM=1.
2026-06-10 · G · DEPTH_AGENTS registry populated (ADK BaseAgent wrappers, guarded import) + run_all_depth fallback; router exported for B to mount. 6/6 depth tests green (schema-validated vs frozen contract). See agents/depth/HANDOFF.md.
2026-06-10 · G · Analytics panel (web/src/features/analytics/) live — $-averted count-up, per-product severity sparklines, recurring-chokepoint bars; fetches {apiBase}/analytics/summary, self-falls-back to embedded golden fixture; quiet/data-dense per design system. Self-contained folder (react + local only).
2026-06-10 · G · company_profile.pharma.json — complete self-contained SECOND vertical (Meridian Therapeutics: APIs/excipients/cold-chain, 14 suppliers/3 products/4 disruptable chains). verify_pharma: schema-valid + referentially consistent + every chain reaches its product. Phase-0 seeder doesn't yet read COMPANY_PROFILE/entities → handoff flagged to Session A. 8/8 tests green.

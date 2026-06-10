# Contract — component isolation boundaries (frontend mounts + depth-agent registry)

> **FROZEN at `phase0`.** Only Session F amends. These are the seams that let Sessions
> E and G build in total isolation while C1 owns the shell and B owns the orchestrator.

## 1. `web/src/features/voice/` — Session E owns internals, C1 owns the mount

Default export: `VoicePanel` (React component). Props (exact):

```ts
export interface VoicePanelProps {
  wsUrl: string;                      // voice gateway base WS URL (VITE_VOICE_WS_URL)
  onIntent: (intent: VoiceIntent) => void;  // C1 forwards to the agent ws as `voice.intent`
  disabled: boolean;                  // true until the gateway is reachable / configured
}
// VoiceIntent mirrors $defs/voice_intent:
export interface VoiceIntent {
  action: "query" | "approve" | "reject" | "show" | "whatif" | "unknown";
  confidence: number;                 // 0..1
  approval_id?: string;
  product_id?: string;
  supplier_id?: string;
  text?: string;
}
```

Rules: the component renders a **disabled mic affordance** when `disabled` (the Phase 0
stub does exactly this — E replaces internals, never the props). It never imports from
outside its folder except `react` and C1's `lib/` (read-only). It talks WS to the voice
gateway itself (`/voice/intent`, `/voice/call` per `http_api.md`); the **only** data it
hands the host app is `onIntent(...)`. C1 forwards that as a ws `voice.intent` message
and routes `approve/reject` intents into the approval flow.

## 2. `web/src/features/analytics/` — Session G owns internals, C1 owns the mount

Default export: `AnalyticsPanel`. Props (exact):

```ts
export interface AnalyticsPanelProps {
  apiBase: string;   // e.g. import.meta.env.VITE_API_BASE — panel fetches `${apiBase}/analytics/summary`
}
```

Rules: fetches `GET {apiBase}/analytics/summary` (`$defs/analytics_summary`); renders the
risk-over-time sparkline per product line, top chokepoints, $-at-risk-avoided counter.
Until the endpoint exists it self-falls-back to the bundled golden fixture
(`contracts/fixtures/analytics_summary.json`) — the stub already does this. No other
network calls, no imports outside its folder except `react` + C1 `lib/` (read-only).

## 3. `agents/depth/` registry — Session G owns internals, B calls it

`agents/depth/__init__.py` exports exactly one symbol B may import:

```python
DEPTH_AGENTS: list  # list of ADK agents (LlmAgent/BaseAgent); SHIPS EMPTY at phase0
```

B's orchestrator, after the Verifier completes (and on what-if runs), iterates
`DEPTH_AGENTS` and runs each with the shared session state. **B's code must behave
identically whether the list is empty or full.** Each depth agent:

| agent | reads state keys | emits (`agent.emit` kind) | side effects |
|---|---|---|---|
| Briefer | `run_meta`, `relevant_events`, `exposure_paths`, `ranked_exposures`, `alternates`, `draft_po`, `verify_result` | `brief` (`$defs/brief_payload`) | report .md/.pdf → GCS; `write_decision(kind:"brief")` |
| Enricher | `relevant_events`, `ranked_exposures` | `ranked_exposures` re-emit with `enriched: true` | `write_decision(kind:"enrich")` |
| BQExport | all of the above | *(none)* | streaming inserts → BigQuery `faultline.runs/exposures/decisions` |

**Shared session-state keys (written by B, read by depth — exact spelling):**
`run_meta` (`{run_id, mode: "live"|"simulated", started_at, scenario?}`),
`relevant_events` (`$defs/relevant_events_payload`),
`exposure_paths` (`$defs/exposure_paths_payload`),
`ranked_exposures` (`$defs/ranked_exposures_payload`),
`alternates` (`$defs/alternates_payload`),
`draft_po` (`$defs/draft_po_payload`),
`verify_result` (`$defs/verify_result_payload`).

Depth agents emit through the same Runner callback as everyone else (so their tool calls
and emissions narrate on the WS automatically). They must never block the core loop:
exceptions are caught and logged by the orchestrator wrapper, not propagated.

## 4. Panel mount points (C1 shell ↔ C2 panels)

C1's shell imports each panel as a default export from its folder — C2 may change
anything **inside** the folders, never the folder path or export shape:

```
web/src/panels/MissionControl/index.tsx   → default export MissionControl
web/src/panels/ActionBoard/index.tsx      → default export ActionBoard
web/src/panels/DecisionLog/index.tsx      → default export DecisionLog
web/src/panels/WhatIf/index.tsx           → default export WhatIf
```

All four receive **no props**. They consume the event stream exclusively via C1's
`lib/` hooks (read-only import): `lib/ws.ts` + `lib/replay.ts` expose one identical
interface (`subscribe(handler: (msg: WsMessage) => void): () => void`) selected by
`VITE_DEMO_MODE` — panels never know which mode they're in. HTTP calls go through
`lib/api.ts` (`postWhatif`, `postApproval`, `reportUrl(runId)`).

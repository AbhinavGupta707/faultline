# STATUS — per-branch heartbeat (append one line per milestone; owned per-branch, never merged across)

2026-06-10 · P0 · Phase 0 bootstrap in progress.

## C2 — Panels (branch ws/c2-panels)

2026-06-10 · C2 · All four panels built and verified end-to-end on replay (ws_replay.jsonl
via C1's getEventStream). Mission Control (goal · numbered plan w/ amber active step ·
streaming tool-call chips with distinct Elastic MCP badges · evidence chips · confidence
meter · Approve/Edit gate wired to approval.decision), Action Board (ranked exposures ·
mono metrics · status pills · expandable alternate+contingent-PO+verify · live call_event
transcript), Decision Log (situation-report header w/ $-averted + GET /report/{run_id}
download · timestamped timeline · evidence chips linking source world-events), What-If
(form + 4 contract presets + magnitude slider → POST /whatif & ws whatif.run · amber
SIMULATED frame). Headless (Playwright/msedge) capture confirms the full SENSE→…→VERIFY
run renders correctly; at_risk→secured transition reflects verify_result. tsc clean for
all C2 files. Swaps replay→live at S2 with zero code change (stream selector is C1's).

### Notes for C1 (lib/) — read-only consumer feedback, NOT edits by C2
- NEW FOLDER: `web/src/panels/_shared/` is C2-owned panel-support (store.ts normalizes the
  ws stream once → useSyncExternalStore; format.ts, ui.tsx, panels.css). Sole writer C2.
  Logged here for F's ownership map (not one of the four named panel folders).
- `lib/replay.ts:24` — `'prev' is possibly null` blocks `tsc -b` (and thus `npm run build`).
  Narrowing is lost inside the setTimeout arrow; hoist `const d = t - prev` before the
  closure or assert. C2 cannot fix (C1 file). Currently the only tsc error in the tree.
- `lib/replay.ts` stops the stream permanently once `handlers.size === 0`. React
  StrictMode's mount→cleanup→remount makes per-component subscribe/unsubscribe hit 0 and
  kill replay. C2 sidesteps it with ONE module-level subscription that never unsubscribes,
  but other consumers (Map, header) may trip on it. Suggest: don't stop on 0, or make the
  stream resumable.
- Boot `status` (seq 0) is delivered synchronously inside `createReplayStream()` before any
  subscriber exists, so it's lost; the next status is at run-end. Header mode chip will read
  empty mid-run. Suggest replaying seq 0 to late subscribers, or buffering the last status.
  (C2's Mission Control infers mode from run data as a workaround.)

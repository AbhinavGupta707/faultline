/** Faultline panel store — the single source of truth for the four C2 panels.
 *
 *  Why this exists: every panel needs a different slice of the SAME ws event
 *  stream (contracts/ws_protocol.md). Rather than have each panel subscribe to
 *  C1's stream directly, we subscribe ONCE here, at module load, and normalize
 *  the firehose into a flat view-model. Panels read it via useSyncExternalStore.
 *
 *  This also sidesteps a fragility in C1's replay harness: `lib/replay.ts` stops
 *  the stream permanently once `handlers.size` hits 0, which React StrictMode's
 *  mount→cleanup→remount cycle triggers if panels subscribe/unsubscribe per-mount.
 *  Our one module-level subscription never unsubscribes, so the count never
 *  returns to 0 and replay plays to completion. (Reported to C1 in STATUS.md.)
 *
 *  C1's lib/ is imported strictly read-only. */

import { useSyncExternalStore } from "react";
import { getEventStream } from "../../lib/stream";
import { postApproval, postWhatif } from "../../lib/api";
import type { WsMessage } from "../../lib/types";
import "./panels.css";

// ── mirrored payload shapes (read-only view of the FROZEN schemas; unknown
//    fields are ignored per the contract's forward-compat rule) ────────────────

export interface GeoPoint { lat: number; lon: number }
export type StepStatus = "pending" | "active" | "done" | "error" | "skipped";
export interface PlanStep { id: string; label: string; status: StepStatus }
export interface PlanState { steps: PlanStep[]; active_step: string | null }

export interface ToolCall {
  call_id: string;
  agent: string;
  tool: string;
  args_summary: string;
  status: "start" | "ok" | "err";
  elastic: boolean;
  latency_ms?: number;
  error?: string;
  ts: string;
  seq: number;
}

export interface RelevantEvent {
  event_id: string;
  title: string;
  source: string;
  event_type: string;
  severity_raw: number;
  location: GeoPoint;
  place_name: string;
  published_at: string;
  url?: string;
  simulated: boolean;
  why_relevant: string;
  supplier_hints?: string[];
}

export interface ExposurePathMatch { score: number; method: string; rationale?: string }
export interface ChainNode { supplier_id: string; name: string; tier: number; role?: string; location?: GeoPoint; country?: string }
export interface ExposurePath {
  path_id: string;
  event_id: string;
  supplier_chain: ChainNode[];
  component_id: string;
  component_name: string;
  product_id: string;
  product_name: string;
  hops: number;
  match: ExposurePathMatch;
}

export type ExposureStatus = "at_risk" | "watch" | "secured";
export interface Exposure {
  exposure_id: string;
  rank: number;
  product_id: string;
  product_name: string;
  component_id: string;
  root_cause_event_id: string;
  chokepoint_supplier_id: string;
  days_of_cover: number;
  est_disruption_days: number;
  dollars_at_risk_usd: number;
  monthly_revenue_usd?: number;
  severity: number;
  status: ExposureStatus;
  rationale: string;
  evidence_event_ids: string[];
  path_ids: string[];
  simulated?: boolean;
}

export interface Alternate {
  supplier_id: string;
  name: string;
  tier?: number;
  location: GeoPoint;
  country: string;
  lead_time_days: number;
  expedited_lead_time_days?: number;
  capacity: string;
  certifications?: string[];
  match_score: number;
  est_unit_cost_usd?: number;
  rationale?: string;
}
export interface AlternatesPayload {
  exposure_id: string;
  component_id: string;
  alternates: Alternate[];
  recommended_supplier_id: string;
}

export interface DraftPO {
  po_id: string;
  run_id?: string;
  exposure_id: string;
  supplier_id: string;
  supplier_name: string;
  component_id: string;
  component_name: string;
  quantity: number;
  unit: string;
  unit_price_usd: number;
  total_usd: number;
  currency?: string;
  incoterms?: string;
  ship_mode?: string;
  need_by_date: string;
  lead_time_days: number;
  contingent: boolean;
  status: string;
  pdf_gcs_uri?: string;
  notes?: string;
  buyer?: string;
}

export interface CallSummary {
  agreed: boolean;
  lead_time_days?: number;
  expedited_lead_time_days?: number;
  quantity?: number;
  unit_price_usd?: number;
  notes?: string;
}
export interface CallEvent {
  call_id: string;
  event: "status" | "transcript" | "summary";
  status?: "initiating" | "ringing" | "connected" | "ended" | "failed";
  speaker?: "faultline_agent" | "supplier";
  text?: string;
  is_final?: boolean;
  summary?: CallSummary;
  ts: string;
}

export interface VerifyResult {
  exposure_id: string;
  product_id: string;
  gap_closed: boolean;
  days_of_cover: number;
  alternate_lead_time_days: number;
  margin_days: number;
  residual_risk: { level: "low" | "medium" | "high"; factors: string[] };
  status_change?: { from: ExposureStatus; to: ExposureStatus };
  summary: string;
  evidence_event_ids: string[];
}

export interface Brief {
  report_id: string;
  run_id: string;
  title: string;
  generated_at: string;
  headline_metric?: { label: string; value: string };
  highlights: string[];
  markdown_gcs_uri?: string;
  pdf_gcs_uri?: string;
  download_path?: string;
  evidence_event_ids: string[];
}

export interface Decision {
  decision_id: string;
  run_id: string;
  ts: string;
  agent: string;
  kind: string;
  summary: string;
  detail?: string;
  evidence_event_ids: string[];
  simulated?: boolean;
  related?: Record<string, unknown>;
}

export interface Approval {
  approval_id: string;
  action_kind: string;
  summary: string;
  requested_by?: string;
  context?: {
    exposure_ids?: string[];
    product_ids?: string[];
    component_id?: string;
    recommended_supplier_id?: string;
    po_id?: string;
    dollars_at_risk_total_usd?: number;
    evidence_event_ids?: string[];
  };
  expires_at?: string;
}

export interface StatusPayload {
  mode: "live" | "simulated";
  feeds_ok: boolean;
  elastic_ok: boolean;
  active_run_id?: string | null;
  note?: string;
}

export interface FaultlineState {
  runId: string | null;
  status: StatusPayload | null;
  plan: PlanState | null;
  toolCalls: ToolCall[];
  relevantEvents: RelevantEvent[];
  eventsById: Record<string, RelevantEvent>;
  exposurePaths: ExposurePath[];
  exposures: Exposure[];
  alternatesByExposure: Record<string, AlternatesPayload>;
  posByExposure: Record<string, DraftPO>;
  callEvents: CallEvent[];
  verifyByExposure: Record<string, VerifyResult>;
  brief: Brief | null;
  decisions: Decision[];
  approval: Approval | null;
  approvalResolved: Record<string, { approved: boolean; note?: string }>;
  /** true when this app is in replay transport (no live backend to POST to). */
  replayMode: boolean;
}

function detectReplayMode(): boolean {
  try {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get("demo") ?? (import.meta.env.VITE_DEMO_MODE as string | undefined) ?? "replay";
    return mode !== "live";
  } catch {
    return true;
  }
}

const EMPTY: FaultlineState = {
  runId: null,
  status: null,
  plan: null,
  toolCalls: [],
  relevantEvents: [],
  eventsById: {},
  exposurePaths: [],
  exposures: [],
  alternatesByExposure: {},
  posByExposure: {},
  callEvents: [],
  verifyByExposure: {},
  brief: null,
  decisions: [],
  approval: null,
  approvalResolved: {},
  replayMode: detectReplayMode(),
};

let state: FaultlineState = EMPTY;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function set(patch: Partial<FaultlineState>) {
  state = { ...state, ...patch };
  emit();
}

// ── reducer over ws messages ─────────────────────────────────────────────────

function handle(msg: WsMessage) {
  const seq = typeof msg.seq === "number" ? msg.seq : 0;
  const runId = msg.run_id ?? state.runId;

  switch (msg.type) {
    case "status":
      set({ status: msg.payload as unknown as StatusPayload, runId });
      break;

    case "plan.update":
      set({ plan: msg.payload as unknown as PlanState, runId });
      break;

    case "tool.call": {
      const p = msg.payload as unknown as Omit<ToolCall, "ts" | "seq">;
      const call: ToolCall = { ...p, ts: msg.ts, seq };
      const existing = state.toolCalls.findIndex((c) => c.call_id === call.call_id);
      let toolCalls: ToolCall[];
      if (existing >= 0) {
        // merge start → ok/err onto the same chip, preserving original order
        toolCalls = state.toolCalls.slice();
        toolCalls[existing] = { ...toolCalls[existing], ...call };
      } else {
        toolCalls = [...state.toolCalls, call];
      }
      set({ toolCalls, runId });
      break;
    }

    case "agent.emit": {
      const { kind, payload } = msg.payload as unknown as { agent: string; kind: string; payload: Record<string, unknown> };
      applyEmit(kind, payload, msg.ts, runId);
      break;
    }

    case "decision.logged": {
      const d = msg.payload as unknown as Decision;
      set({ decisions: [...state.decisions, d], runId });
      break;
    }

    case "approval.request": {
      const a = msg.payload as unknown as Approval;
      set({ approval: a, runId });
      break;
    }

    case "approval.decision": {
      // echoed scripted line in replay; record resolution
      const p = msg.payload as unknown as { approval_id: string; approved: boolean; note?: string };
      resolveApproval(p.approval_id, p.approved, p.note);
      break;
    }

    default:
      break;
  }
}

function applyEmit(kind: string, payload: Record<string, unknown>, ts: string, runId: string | null) {
  switch (kind) {
    case "relevant_events": {
      const events = ((payload.events as RelevantEvent[]) ?? []).slice();
      const eventsById = { ...state.eventsById };
      for (const e of events) eventsById[e.event_id] = e;
      set({ relevantEvents: events, eventsById, runId });
      break;
    }
    case "exposure_paths": {
      const paths = (payload.paths as ExposurePath[]) ?? [];
      set({ exposurePaths: paths, runId });
      break;
    }
    case "ranked_exposures": {
      const exposures = (payload.exposures as Exposure[]) ?? [];
      // patch any already-secured statuses back in (verify may have arrived first
      // in theory; in practice ranked_exposures comes first)
      set({ exposures, runId });
      break;
    }
    case "alternates": {
      const ap = payload as unknown as AlternatesPayload;
      set({ alternatesByExposure: { ...state.alternatesByExposure, [ap.exposure_id]: ap }, runId });
      break;
    }
    case "draft_po": {
      const po = payload as unknown as DraftPO;
      set({ posByExposure: { ...state.posByExposure, [po.exposure_id]: po }, runId });
      break;
    }
    case "call_event": {
      const ce = { ...(payload as unknown as CallEvent), ts };
      set({ callEvents: [...state.callEvents, ce], runId });
      break;
    }
    case "verify_result": {
      const vr = payload as unknown as VerifyResult;
      const verifyByExposure = { ...state.verifyByExposure, [vr.exposure_id]: vr };
      // reflect the secured transition onto the ranked exposure immediately
      let exposures = state.exposures;
      if (vr.status_change) {
        exposures = state.exposures.map((e) =>
          e.exposure_id === vr.exposure_id ? { ...e, status: vr.status_change!.to } : e,
        );
      }
      set({ verifyByExposure, exposures, runId });
      break;
    }
    case "brief": {
      set({ brief: payload as unknown as Brief, runId });
      break;
    }
    default:
      break;
  }
}

function resolveApproval(approval_id: string, approved: boolean, note?: string) {
  set({
    approvalResolved: { ...state.approvalResolved, [approval_id]: { approved, note } },
    approval: state.approval?.approval_id === approval_id ? null : state.approval,
  });
}

// ── actions (client → server) ────────────────────────────────────────────────

/** Resolve the pending approval. ws + http are equivalent & idempotent per contract.
 *  We update the UI optimistically; in replay both transports are inert no-ops, and
 *  the scripted run continues on its own timeline. */
export function decideApproval(approval_id: string, approved: boolean, note?: string) {
  resolveApproval(approval_id, approved, note);
  try {
    getEventStream().send({
      type: "approval.decision",
      ts: new Date().toISOString(),
      run_id: state.runId,
      payload: { approval_id, approved, ...(note ? { note } : {}) },
    } as WsMessage);
  } catch {
    /* replay send is a no-op */
  }
  void postApproval(approval_id, approved, note).catch(() => {});
}

export interface WhatifScenario {
  preset?: string;
  title?: string;
  event_type: string;
  location: GeoPoint;
  place_name?: string;
  duration_days: number;
  magnitude: number;
}

/** Launch a what-if. Equivalent ws `whatif.run` + `POST /whatif`. In live mode the
 *  identical pipeline streams `simulated:true` results back through this same store. */
export function runWhatif(scenario: WhatifScenario): Promise<{ accepted: boolean; run_id?: string; event_id?: string }> {
  try {
    getEventStream().send({
      type: "whatif.run",
      ts: new Date().toISOString(),
      run_id: state.runId,
      payload: { scenario },
    } as WsMessage);
  } catch {
    /* replay send is a no-op */
  }
  return postWhatif(scenario as unknown as Record<string, unknown>).catch(() => ({
    accepted: false,
    run_id: undefined,
    event_id: undefined,
  })) as Promise<{ accepted: boolean; run_id?: string; event_id?: string }>;
}

// ── React binding ────────────────────────────────────────────────────────────

let started = false;
function start() {
  if (started) return;
  started = true;
  getEventStream().subscribe(handle);
}
start();

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}
function getSnapshot(): FaultlineState {
  return state;
}

export function useFaultline(): FaultlineState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** Narrow selector hook to limit re-renders for leaf widgets if needed. */
export function useFaultlineSelector<T>(selector: (s: FaultlineState) => T): T {
  return useSyncExternalStore(
    subscribe,
    () => selector(state),
    () => selector(state),
  );
}

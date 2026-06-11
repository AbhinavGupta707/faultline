/** WS message types — mirrors contracts/ws_protocol.md + schemas/faultline.schema.json.
 *  Session C1 owns this file; consumers (C2/E/G panels) import read-only.
 *  Compatibility rule (contract): required fields are strict; ignore unknown extras. */

export type WsType =
  | "plan.update"
  | "tool.call"
  | "agent.emit"
  | "decision.logged"
  | "approval.request"
  | "status"
  | "approval.decision"
  | "whatif.run"
  | "chat"
  | "voice.intent";

export type EmitKind =
  | "relevant_events"
  | "exposure_paths"
  | "ranked_exposures"
  | "alternates"
  | "draft_po"
  | "call_event"
  | "verify_result"
  | "brief";

export interface WsMessage<P = Record<string, unknown>> {
  type: WsType;
  ts: string;
  run_id: string | null;
  seq?: number;
  dir?: "s2c" | "c2s"; // only present in ws_replay.jsonl choreography lines
  payload: P;
}

export interface AgentEmitPayload {
  agent: string;
  kind: EmitKind;
  payload: Record<string, unknown>;
}

export type StreamHandler = (msg: WsMessage) => void;

/** The single interface both lib/ws.ts (live) and lib/replay.ts (fixture) implement.
 *  Selected by VITE_DEMO_MODE — panels never know which mode they are in. */
export interface EventStream {
  subscribe(handler: StreamHandler): () => void;
  send(msg: WsMessage): void; // c2s: approval.decision | whatif.run | chat | voice.intent
}

/* ----------------------------------------------------------------------------
 * Payload shapes (subset that C1 reads to derive map + header visuals).
 * Only the fields the shell/map use are typed; consumers ignore unknown extras.
 * -------------------------------------------------------------------------- */

export type PlanStepStatus = "pending" | "active" | "done";
export interface PlanStep {
  id: string;
  label: string;
  status: PlanStepStatus;
}
export interface PlanUpdatePayload {
  steps: PlanStep[];
  active_step: string | null;
}

export interface ToolCallPayload {
  call_id: string;
  agent: string;
  tool: string;
  args_summary: string;
  status: "start" | "ok" | "err";
  elastic: boolean;
  latency_ms?: number;
  error?: string;
}

export interface GeoPoint { lat: number; lon: number; }

export interface StatusPayload {
  mode: "live" | "simulated";
  feeds_ok: boolean;
  elastic_ok: boolean;
  active_run_id?: string | null;
  note?: string;
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
  simulated?: boolean;
  why_relevant?: string;
  supplier_hints?: string[];
}
export interface RelevantEventsPayload {
  considered_count?: number;
  events: RelevantEvent[];
}

export interface ChainNode {
  supplier_id: string;
  name: string;
  tier: number;
  role?: string;
  location: GeoPoint;
  country?: string;
}
export interface ExposurePath {
  path_id: string;
  event_id: string;
  supplier_chain: ChainNode[];
  component_id: string;
  product_id: string;
  product_name: string;
  hops: number;
}
export interface ExposurePathsPayload {
  event_id: string;
  paths: ExposurePath[];
}

export type ExposureStatus = "at_risk" | "watch" | "secured";
export interface RankedExposure {
  exposure_id: string;
  rank: number;
  product_id: string;
  product_name: string;
  component_id?: string;
  chokepoint_supplier_id?: string;
  days_of_cover: number;
  est_disruption_days?: number;
  dollars_at_risk_usd: number;
  severity: number;
  status: ExposureStatus;
  root_cause_event_id?: string;
  path_ids?: string[];
}
export interface RankedExposuresPayload {
  exposures: RankedExposure[];
  enriched?: boolean;
}

export interface Alternate {
  supplier_id: string;
  name: string;
  location: GeoPoint;
  lead_time_days: number;
  match_score: number;
}
export interface AlternatesPayload {
  exposure_id: string;
  component_id: string;
  recommended_supplier_id: string;
  alternates: Alternate[];
}

export interface VerifyResultPayload {
  exposure_id: string;
  product_id: string;
  gap_closed: boolean;
  days_of_cover?: number;
  alternate_lead_time_days?: number;
  margin_days?: number;
  status_change?: { from: ExposureStatus; to: ExposureStatus };
}

export interface ApprovalRequestPayload {
  approval_id: string;
  action_kind: string;
  summary: string;
  context?: Record<string, unknown>;
}

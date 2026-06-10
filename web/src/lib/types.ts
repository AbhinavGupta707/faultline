/** WS message types — mirrors contracts/ws_protocol.md + schemas/faultline.schema.json.
 *  Session C1 owns this file; consumers (C2/E/G panels) import read-only. */

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

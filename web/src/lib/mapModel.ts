/** mapModel — the heart of the living map (Session C1 owns).
 *  A PURE reducer that derives every map visual from the semantic WS stream
 *  (agent.emit / plan.update / status). The backend never sends pixels: ripples,
 *  hot arcs, igniting/cooling product nodes and the gold scan-pulse are all inferred
 *  here from `relevant_events`, `exposure_paths`, `ranked_exposures`, `alternates`,
 *  and `verify_result`. See contracts/ws_protocol.md §"agent.emit kinds → map effect". */
import { edgeKey } from "./map/network";
import { nodeById } from "./map/network";
import type {
  AgentEmitPayload,
  AlternatesPayload,
  ExposurePathsPayload,
  ExposureStatus,
  PlanStep,
  PlanUpdatePayload,
  RankedExposuresPayload,
  RelevantEventsPayload,
  StatusPayload,
  VerifyResultPayload,
  WsMessage,
} from "./types";

export interface Ripple {
  eventId: string;
  lon: number;
  lat: number;
  severity: number;
  title: string;
  placeName: string;
  eventType: string;
  simulated: boolean;
}

export interface ProductExposure {
  status: ExposureStatus;
  daysOfCover: number;
  dollarsAtRisk: number;
  severity: number;
}

export interface Focus {
  lon: number;
  lat: number;
  label: string;
}

export interface SecuredSummary {
  productId: string;
  supplierName: string;
  leadDays?: number;
  coverDays?: number;
}

export interface MapState {
  mode: "live" | "simulated";
  feedsOk: boolean;
  elasticOk: boolean;
  statusNote: string;
  activeRunId: string | null;
  simulated: boolean;

  steps: PlanStep[];
  activeStep: string | null;
  phase: string; // active step id, or "done"/"idle"

  ripples: Ripple[];
  hotEdgeKeys: Set<string>; // "src>dst" arcs that pulse coral
  exposureByProduct: Record<string, ProductExposure>;
  secured: Set<string>; // product ids cooled to mint
  altCandidates: Set<string>; // candidate supplier ids (highlight)
  recommended: string | null; // gold scan-pulse supplier
  focus: Focus | null; // agent's current scan focus
  approvalPending: { approval_id: string; summary: string } | null;
  lastSecured: SecuredSummary | null; // drives the "secured" narration callout
}

export function initialMapState(): MapState {
  return {
    mode: "live",
    feedsOk: false,
    elasticOk: false,
    statusNote: "Connecting…",
    activeRunId: null,
    simulated: false,
    steps: [],
    activeStep: null,
    phase: "idle",
    ripples: [],
    hotEdgeKeys: new Set(),
    exposureByProduct: {},
    secured: new Set(),
    altCandidates: new Set(),
    recommended: null,
    focus: null,
    approvalPending: null,
    lastSecured: null,
  };
}

function applyEmit(s: MapState, emit: AgentEmitPayload): void {
  const p = emit.payload as Record<string, unknown>;
  switch (emit.kind) {
    case "relevant_events": {
      const ev = p as unknown as RelevantEventsPayload;
      for (const e of ev.events ?? []) {
        if (s.ripples.some((r) => r.eventId === e.event_id)) continue;
        s.ripples.push({
          eventId: e.event_id,
          lon: e.location.lon,
          lat: e.location.lat,
          severity: e.severity_raw ?? 0.5,
          title: e.title,
          placeName: e.place_name,
          eventType: e.event_type,
          simulated: e.simulated ?? false,
        });
      }
      const first = ev.events?.[0];
      if (first) s.focus = { lon: first.location.lon, lat: first.location.lat, label: first.place_name };
      break;
    }
    case "exposure_paths": {
      const ep = p as unknown as ExposurePathsPayload;
      let chokepoint: string | null = null;
      for (const path of ep.paths ?? []) {
        const chain = path.supplier_chain ?? [];
        if (!chokepoint && chain[0]) chokepoint = chain[0].supplier_id;
        for (let i = 0; i < chain.length - 1; i++) {
          s.hotEdgeKeys.add(edgeKey(chain[i].supplier_id, chain[i + 1].supplier_id));
        }
        const last = chain[chain.length - 1];
        if (last) s.hotEdgeKeys.add(edgeKey(last.supplier_id, path.product_id));
      }
      if (chokepoint) {
        const n = nodeById(chokepoint);
        if (n) s.focus = { lon: n.lon, lat: n.lat, label: n.name };
      }
      break;
    }
    case "ranked_exposures": {
      const re = p as unknown as RankedExposuresPayload;
      for (const ex of re.exposures ?? []) {
        const prev = s.exposureByProduct[ex.product_id];
        // keep the most severe exposure per product
        if (!prev || ex.severity >= prev.severity) {
          s.exposureByProduct[ex.product_id] = {
            status: ex.status,
            daysOfCover: ex.days_of_cover,
            dollarsAtRisk: ex.dollars_at_risk_usd,
            severity: ex.severity,
          };
        }
      }
      break;
    }
    case "alternates": {
      const al = p as unknown as AlternatesPayload;
      for (const a of al.alternates ?? []) s.altCandidates.add(a.supplier_id);
      s.recommended = al.recommended_supplier_id ?? null;
      const n = s.recommended ? nodeById(s.recommended) : undefined;
      if (n) s.focus = { lon: n.lon, lat: n.lat, label: n.name };
      break;
    }
    case "verify_result": {
      const vr = p as unknown as VerifyResultPayload;
      if (vr.status_change?.to === "secured" || vr.gap_closed) {
        s.secured.add(vr.product_id);
        const ex = s.exposureByProduct[vr.product_id];
        if (ex) ex.status = "secured";
        s.lastSecured = {
          productId: vr.product_id,
          supplierName: s.recommended ? nodeById(s.recommended)?.name ?? "alternate supplier" : "alternate supplier",
          leadDays: vr.alternate_lead_time_days,
          coverDays: vr.days_of_cover,
        };
      }
      break;
    }
    default:
      break; // draft_po, call_event, brief → not map-bound
  }
}

/** Reduce the full accumulated message log into the current map state. */
export function reduceMapState(messages: WsMessage[]): MapState {
  const s = initialMapState();
  for (const msg of messages) {
    switch (msg.type) {
      case "status": {
        const st = msg.payload as unknown as StatusPayload;
        s.mode = st.mode;
        s.simulated = st.mode === "simulated";
        s.feedsOk = !!st.feeds_ok;
        s.elasticOk = !!st.elastic_ok;
        if (st.note) s.statusNote = st.note;
        s.activeRunId = st.active_run_id ?? msg.run_id ?? s.activeRunId;
        break;
      }
      case "plan.update": {
        const pu = msg.payload as unknown as PlanUpdatePayload;
        s.steps = pu.steps ?? [];
        s.activeStep = pu.active_step ?? null;
        s.phase = pu.active_step ?? (s.steps.length && s.steps.every((x) => x.status === "done") ? "done" : s.phase);
        break;
      }
      case "agent.emit":
        applyEmit(s, msg.payload as unknown as AgentEmitPayload);
        break;
      case "approval.request": {
        const ar = msg.payload as { approval_id: string; summary: string };
        s.approvalPending = { approval_id: ar.approval_id, summary: ar.summary };
        break;
      }
      case "decision.logged": {
        const d = msg.payload as { kind?: string };
        if (d.kind === "approval") s.approvalPending = null;
        break;
      }
      default:
        break;
    }
  }
  return s;
}

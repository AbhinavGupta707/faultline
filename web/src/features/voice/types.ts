// Voice feature types. The public surface (VoiceIntent, VoicePanelProps) is re-exported
// from index.tsx so the FROZEN component contract (contracts/components.md §1) is unchanged.

export interface VoiceIntent {
  action: "query" | "approve" | "reject" | "show" | "whatif" | "unknown";
  confidence: number;
  approval_id?: string;
  product_id?: string;
  supplier_id?: string;
  text?: string;
}

export interface VoicePanelProps {
  wsUrl: string; // voice gateway base WS URL (VITE_VOICE_WS_URL), e.g. ws://localhost:8082
  onIntent: (intent: VoiceIntent) => void; // C1 forwards to the agent ws as `voice.intent`
  disabled: boolean; // true until the gateway is reachable / configured
}

// ── gateway wire messages (http_api.md voice_gateway) ──────────────────────────
export type Speaker = "faultline_agent" | "supplier";

export interface CallEventPayload {
  call_id: string;
  event: "status" | "transcript" | "summary";
  status?: "initiating" | "ringing" | "connected" | "ended" | "failed";
  speaker?: Speaker;
  text?: string;
  is_final?: boolean;
  summary?: {
    agreed: boolean;
    lead_time_days?: number;
    expedited_lead_time_days?: number;
    quantity?: number;
    unit_price_usd?: number;
    notes?: string;
  };
}

export interface CallTurn {
  speaker: Speaker;
  text: string;
}

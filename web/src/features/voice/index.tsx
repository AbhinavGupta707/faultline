/** Voice overlay — Session E owns this folder's internals; props are FROZEN
 *  (contracts/components.md §1). Phase 0 stub: disabled mic affordance. */

export interface VoiceIntent {
  action: "query" | "approve" | "reject" | "show" | "whatif" | "unknown";
  confidence: number;
  approval_id?: string;
  product_id?: string;
  supplier_id?: string;
  text?: string;
}

export interface VoicePanelProps {
  wsUrl: string;
  onIntent: (intent: VoiceIntent) => void;
  disabled: boolean;
}

export default function VoicePanel({ disabled }: VoicePanelProps) {
  return (
    <button
      type="button"
      disabled
      aria-label="Push to talk (voice coming online)"
      title={disabled ? "Voice gateway not connected" : "Push to talk"}
      className="mono"
      style={{
        width: 40, height: 40, borderRadius: "50%",
        background: "var(--panel)", border: "1px solid var(--hairline)",
        color: "var(--ink-dim)", cursor: "not-allowed",
      }}
    >
      ●
    </button>
  );
}

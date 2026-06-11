/** Live narration line (Session C1 owns) — a plain-English status line on the map that
 *  says what the agent is doing RIGHT NOW, from plan.active_step + the latest tool call:
 *  "Tracing exposure paths — asking Elastic which suppliers sit in the affected zone…".
 *  Kills the is-it-stuck feeling during live/simulated runs. Hidden when idle/complete. */
import type { MapState } from "../../lib/mapModel";

const PHASE_VERB: Record<string, string> = {
  scan: "Scanning world events",
  trace: "Tracing exposure paths",
  assess: "Quantifying exposure",
  approve: "Awaiting your approval",
  resource: "Securing alternate supply",
  verify: "Verifying coverage",
};

const TOOL_PHRASE: Record<string, string> = {
  search_events: "scanning the live feeds for relevant events",
  match_event_to_suppliers: "asking Elastic which suppliers sit in the affected zone",
  traverse_supply_graph: "tracing the supply graph through to finished products",
  lookup_exposure: "checking days of cover and revenue at risk",
  find_alternate_suppliers: "asking Elastic for qualified alternate suppliers",
  generate_po_pdf: "drafting the contingent purchase order",
  write_decision: "logging the decision with linked evidence",
};

function narrate(state: MapState): string | null {
  const step = state.activeStep;
  if (!step || state.phase === "done") return null;
  const phase = PHASE_VERB[step] ?? "Working";
  // the approval gate is a deliberate wait on the human — say so, don't narrate a tool
  if (step === "approve") return `${phase} — review the re-source recommendation`;
  const t = state.lastTool;
  const detail = t ? TOOL_PHRASE[t.tool] ?? (t.elastic ? "querying Elastic" : "working") : null;
  return detail ? `${phase} — ${detail}` : phase;
}

export default function NarrationLine({ state, bottom }: { state: MapState; bottom: number }) {
  const text = narrate(state);
  if (!text) return null;
  return (
    <div
      className="fade-up"
      style={{
        position: "absolute",
        left: 16,
        bottom,
        maxWidth: "66%",
        display: "flex",
        alignItems: "center",
        gap: 8,
        pointerEvents: "none",
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: "var(--signal)",
          boxShadow: "var(--glow-amber)",
          flexShrink: 0,
          animation: "fl-pulse 1.4s ease-in-out infinite",
        }}
      />
      <span style={{ fontSize: 12.5, color: "var(--ink)", letterSpacing: "0.01em", lineHeight: 1.3 }}>
        {text}
        <span className="dim">…</span>
      </span>
    </div>
  );
}

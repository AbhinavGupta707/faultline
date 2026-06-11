/** Faultline app shell — Session C1 owns. Cartographic control tower frame:
 *  the living map is the one bold signature; the right rail stays quiet and data-dense.
 *  All panel + feature mount points per contracts/components.md render gracefully while
 *  their owning sessions (C2 panels, E voice, G analytics) are still stubbed. */
import { useMemo } from "react";
import MapPanel from "./panels/Map";
import MissionControl from "./panels/MissionControl";
import ActionBoard from "./panels/ActionBoard";
import DecisionLog from "./panels/DecisionLog";
import WhatIf from "./panels/WhatIf";
import AnalyticsPanel from "./features/analytics";
import { API_BASE } from "./lib/api";
import { useEventStream } from "./lib/useStream";
import { reduceMapState } from "./lib/mapModel";

function isReplay(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("demo") === "replay";
  } catch {
    return false;
  }
}

export default function App() {
  const { messages } = useEventStream();
  const state = useMemo(() => reduceMapState(messages), [messages]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 12, gap: 12 }}>
      <header style={{ display: "flex", alignItems: "center", gap: 14, padding: "0 4px" }}>
        <span style={{ fontWeight: 700, letterSpacing: "0.16em", fontSize: 14, flexShrink: 0 }}>FAULTLINE</span>
        <span className="eyebrow" style={{ marginTop: 1, flexShrink: 0 }}>Supply Chain Control Tower</span>

        {/* run status — flexes to fill, ellipsizes only when genuinely cramped */}
        <span
          className="mono dim"
          title={state.statusNote}
          style={{ flex: "1 1 auto", minWidth: 0, textAlign: "right", fontSize: 11, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {state.statusNote}
        </span>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          {/* always-visible demo entry point — judges must never wonder how to see the show */}
          <a
            href={isReplay() ? window.location.pathname : "?demo=replay"}
            title={isReplay() ? "Return to live mode — real world events, real agent runs" : "Play a scripted end-to-end incident (70s)"}
            style={{
              textDecoration: "none", fontSize: 11, letterSpacing: "0.08em", fontWeight: 600,
              padding: "5px 12px", borderRadius: 14, whiteSpace: "nowrap",
              color: isReplay() ? "var(--ink, #E6EDF6)" : "#0A1422",
              background: isReplay() ? "transparent" : "var(--signal, #F5B544)",
              border: "1px solid var(--signal, #F5B544)",
            }}
          >
            {isReplay() ? "● GO LIVE" : "▶ WATCH DEMO"}
          </a>
          <span className={"chip " + (state.feedsOk ? "ok" : "err")}>
            <span className="dot" /> feeds
          </span>
          <span className={"chip " + (state.elasticOk ? "ok" : "err")}>
            <span className="dot" /> elastic
          </span>
          <span className={"chip " + (state.simulated ? "sim" : "ok")}>
            <span className="dot" /> {state.simulated ? "simulated" : "live"}
          </span>
        </div>
      </header>

      <main style={{ display: "grid", gridTemplateColumns: "minmax(0, 2.1fr) minmax(330px, 1fr)", gap: 12, flex: 1, minHeight: 0 }}>
        {/* map column — relative so the voice affordance can anchor over its bottom-center */}
        <div style={{ position: "relative", minWidth: 0, minHeight: 0 }}>
          <MapPanel />
          {/* Voice push-to-talk (Session E's VoicePanel) is intentionally NOT mounted on the
              demo surface: it shipped `disabled` (a dead control reads as a bug to judges —
              "no dead buttons on camera"). The voice story is carried by the negotiation-call
              transcript + its audio playback; re-enable here post-event when the in-app
              gateway round-trip is verified. */}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0, overflow: "auto" }}>
          <MissionControl />
          <ActionBoard />
          <DecisionLog />
          <WhatIf />
          {/* Analytics is depth, not run-critical — default-collapsed so the run panels
              own the rail; a click expands the full live BigQuery history. */}
          <details className="fl-analytics-fold">
            <summary
              style={{
                cursor: "pointer", listStyle: "none", padding: "9px 12px",
                fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase",
                color: "var(--text-dim, #7c8ba1)", background: "var(--panel, #13202b)",
                border: "1px solid var(--panel-border, #2c3a4d)", borderRadius: 8,
                userSelect: "none", display: "flex", alignItems: "center", gap: 8,
              }}
            >
              <span style={{ opacity: 0.7 }}>▸</span>
              Analytics · 60-day risk history
            </summary>
            <div style={{ marginTop: 12 }}>
              <AnalyticsPanel apiBase={API_BASE} />
            </div>
          </details>
        </div>
      </main>
    </div>
  );
}

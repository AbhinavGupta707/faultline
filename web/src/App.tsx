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
import VoicePanel from "./features/voice";
import AnalyticsPanel from "./features/analytics";
import { API_BASE } from "./lib/api";
import { useEventStream } from "./lib/useStream";
import { reduceMapState } from "./lib/mapModel";

export default function App() {
  const { messages, send } = useEventStream();
  const state = useMemo(() => reduceMapState(messages), [messages]);

  const onIntent = (intent: { action: string; approval_id?: string }) => {
    // C1 forwards voice intents onto the agent ws; approve/reject route into the gate.
    send({
      type: "voice.intent",
      ts: new Date().toISOString(),
      run_id: state.activeRunId,
      payload: { intent },
    });
  };

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
          {/* voice affordance sits bottom-center, lifted clear of the intel ticker strip */}
          <div style={{ position: "absolute", bottom: 44, left: "50%", transform: "translateX(-50%)", zIndex: 6 }}>
            <VoicePanel wsUrl={import.meta.env.VITE_VOICE_WS_URL ?? ""} onIntent={onIntent} disabled />
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0, overflow: "auto" }}>
          <MissionControl />
          <ActionBoard />
          <DecisionLog />
          <WhatIf />
          <AnalyticsPanel apiBase={API_BASE} />
        </div>
      </main>
    </div>
  );
}

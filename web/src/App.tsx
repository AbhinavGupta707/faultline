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
        <span style={{ fontWeight: 700, letterSpacing: "0.16em", fontSize: 14 }}>FAULTLINE</span>
        <span className="eyebrow" style={{ marginTop: 1 }}>Supply Chain Control Tower</span>

        <span className="mono dim" style={{ marginLeft: "auto", fontSize: 11, maxWidth: 360, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {state.statusNote}
        </span>

        <span className={"chip " + (state.feedsOk ? "ok" : "err")}>
          <span className="dot" /> feeds
        </span>
        <span className={"chip " + (state.elasticOk ? "ok" : "err")}>
          <span className="dot" /> elastic
        </span>
        <span className={"chip " + (state.simulated ? "sim" : "ok")}>
          <span className="dot" /> {state.simulated ? "simulated" : "live"}
        </span>

        <VoicePanel wsUrl={import.meta.env.VITE_VOICE_WS_URL ?? ""} onIntent={onIntent} disabled />
      </header>

      <main style={{ display: "grid", gridTemplateColumns: "minmax(0, 2.1fr) minmax(330px, 1fr)", gap: 12, flex: 1, minHeight: 0 }}>
        <MapPanel />
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

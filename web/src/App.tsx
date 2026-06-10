/** Faultline app shell — Session C1 owns. All mount points per contracts/components.md.
 *  Phase 0: dark control-tower frame with every panel stubbed. */
import MapPanel from "./panels/Map";
import MissionControl from "./panels/MissionControl";
import ActionBoard from "./panels/ActionBoard";
import DecisionLog from "./panels/DecisionLog";
import WhatIf from "./panels/WhatIf";
import VoicePanel from "./features/voice";
import AnalyticsPanel from "./features/analytics";
import { API_BASE } from "./lib/api";

export default function App() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 10, gap: 10 }}>
      <header style={{ display: "flex", alignItems: "center", gap: 12, padding: "2px 6px" }}>
        <span style={{ fontWeight: 600, letterSpacing: "0.08em" }}>FAULTLINE</span>
        <span className="eyebrow">Supply Chain Control Tower</span>
        <span className="mono dim" style={{ marginLeft: "auto", fontSize: 11 }}>
          mode: replay · feeds: — · elastic: —
        </span>
        <VoicePanel wsUrl={import.meta.env.VITE_VOICE_WS_URL ?? ""} onIntent={() => {}} disabled />
      </header>

      <main style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10, flex: 1, minHeight: 0 }}>
        <MapPanel />
        <div style={{ display: "flex", flexDirection: "column", gap: 10, minHeight: 0, overflow: "auto" }}>
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

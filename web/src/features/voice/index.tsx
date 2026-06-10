/** Voice overlay — Session E owns this folder's internals; props are FROZEN
 *  (contracts/components.md §1). Push-to-talk voice-in (→ onIntent) + the in-app
 *  negotiation call (waveform + transcript + amber "AI agent speaking" indicator). */

import { useState } from "react";
import Waveform from "./Waveform";
import { useNegotiationCall } from "./useNegotiationCall";
import { useVoiceIntent } from "./useVoiceIntent";
import type { VoiceIntent, VoicePanelProps } from "./types";

// Re-export the frozen public types from the canonical entry point.
export type { VoiceIntent, VoicePanelProps } from "./types";

const AMBER = "var(--amber, #f5a623)";
const TEAL = "var(--teal, #2dd4bf)";
const PANEL = "var(--panel, #0f2030)";
const HAIR = "var(--hairline, #1d3b54)";
const INK = "var(--ink, #dce8f2)";
const INK_DIM = "var(--ink-dim, #7e98ad)";

const ACTION_LABEL: Record<VoiceIntent["action"], string> = {
  query: "Query", approve: "Approve", reject: "Reject",
  show: "Focus map", whatif: "What-if", unknown: "Unclear",
};

export default function VoicePanel({ wsUrl, onIntent, disabled }: VoicePanelProps) {
  const [open, setOpen] = useState(false);
  const voice = useVoiceIntent(wsUrl, onIntent);
  const call = useNegotiationCall(wsUrl);

  // Disabled stub behaviour (unchanged from Phase 0): a non-interactive mic affordance.
  if (disabled) {
    return (
      <button
        type="button"
        disabled
        aria-label="Push to talk (voice coming online)"
        title="Voice gateway not connected"
        className="mono"
        style={micStyle(false, true)}
      >
        ●
      </button>
    );
  }

  const showCard = open || voice.recording || !!voice.lastIntent || call.active || call.turns.length > 0;

  return (
    <div style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 8 }}>
      <button
        type="button"
        aria-label="Push to talk"
        aria-pressed={voice.recording}
        title="Hold to talk"
        className="mono"
        style={micStyle(voice.recording, false)}
        onPointerDown={(e) => {
          e.preventDefault();
          setOpen(true);
          void voice.startTalking();
        }}
        onPointerUp={() => voice.stopTalking()}
        onPointerLeave={() => voice.recording && voice.stopTalking()}
      >
        ●
      </button>

      {showCard && (
        <div role="dialog" aria-label="Voice" style={cardStyle}>
          <Header onClose={() => setOpen(false)} />

          {/* Voice IN */}
          <Section label="Voice in">
            <div style={{ minHeight: 20, color: INK_DIM, fontSize: 13 }}>
              {voice.recording
                ? voice.partial || "Listening…"
                : voice.lastIntent
                  ? `“${voice.lastIntent.text ?? voice.partial}”`
                  : "Hold the mic and speak."}
            </div>
            {voice.lastIntent && !voice.recording && (
              <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
                <span style={chip(intentColor(voice.lastIntent.action))}>
                  {ACTION_LABEL[voice.lastIntent.action]}
                </span>
                <span style={{ color: INK_DIM, fontSize: 12 }}>
                  {(voice.lastIntent.confidence * 100) | 0}% confidence
                </span>
              </div>
            )}
            <Speaking on={voice.ackSpeaking} />
          </Section>

          {/* Voice OUT */}
          <Section label="Negotiation call">
            {!call.active && call.turns.length === 0 ? (
              <button type="button" style={btn(TEAL)} onClick={() => call.startCall()}>
                ▶ Call alternate supplier
              </button>
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="mono" style={{ fontSize: 11, color: INK_DIM }}>
                    {call.status || "…"}
                  </span>
                  {call.active && (
                    <button type="button" style={btn("#ff6b5e")} onClick={() => call.endCall()}>
                      ■ End
                    </button>
                  )}
                </div>
                <Speaking
                  on={!!call.speaker}
                  label={call.speaker === "supplier" ? "Supplier speaking" : "AI agent speaking"}
                />
                <div style={{ marginTop: 8 }}>
                  <Waveform getAnalyser={call.analyser} active={call.active} />
                </div>
                <div style={{ marginTop: 10, maxHeight: 220, overflow: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
                  {call.turns.map((t, i) => (
                    <Turn key={i} agent={t.speaker === "faultline_agent"} text={t.text} />
                  ))}
                </div>
                {call.summary && (
                  <div style={summaryStyle(call.summary.agreed)}>
                    {call.summary.agreed ? "✓ Agreed" : "✗ No deal"} · contingent on PO approval
                    {call.summary.notes ? ` — ${call.summary.notes}` : ""}
                  </div>
                )}
              </>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}

// ── small presentational helpers ────────────────────────────────────────────────
function Header({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
      <span style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase", color: INK_DIM }}>
        ✦ Faultline voice
      </span>
      <button type="button" aria-label="Close" onClick={onClose}
        style={{ background: "none", border: "none", color: INK_DIM, cursor: "pointer", fontSize: 14 }}>
        ✕
      </button>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ borderTop: `1px solid ${HAIR}`, paddingTop: 10, marginTop: 10 }}>
      <div style={{ fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase", color: INK_DIM, marginBottom: 6 }}>
        {label}
      </div>
      {children}
    </div>
  );
}

function Speaking({ on, label = "AI agent speaking" }: { on: boolean; label?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, height: 18, fontSize: 12, color: on ? AMBER : INK_DIM }}>
      <span
        style={{
          width: 9, height: 9, borderRadius: "50%",
          background: on ? AMBER : "#2a4258",
          boxShadow: on ? `0 0 10px ${AMBER}` : "none",
          transition: "background .2s",
        }}
      />
      {on ? label : "idle"}
    </div>
  );
}

function Turn({ agent, text }: { agent: boolean; text: string }) {
  return (
    <div
      style={{
        padding: "8px 10px", borderRadius: 8, background: "var(--panel2, #13283b)",
        borderLeft: `3px solid ${agent ? AMBER : TEAL}`, fontSize: 13, color: INK,
      }}
    >
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 3, color: agent ? AMBER : TEAL }}>
        {agent ? "Faultline AI agent" : "Supplier (role-play)"}
      </div>
      {text}
    </div>
  );
}

// ── style helpers ───────────────────────────────────────────────────────────────
function micStyle(recording: boolean, dis: boolean): React.CSSProperties {
  return {
    width: 40, height: 40, borderRadius: "50%",
    background: recording ? "#3a1714" : PANEL,
    border: `1px solid ${recording ? "#ff6b5e" : HAIR}`,
    color: recording ? "#ff6b5e" : dis ? INK_DIM : INK,
    cursor: dis ? "not-allowed" : "pointer",
    boxShadow: recording ? "0 0 0 6px rgba(255,107,94,.15)" : "none",
    transition: ".15s",
  };
}

const cardStyle: React.CSSProperties = {
  position: "absolute", top: 48, right: 0, width: 340, zIndex: 50,
  background: PANEL, border: `1px solid ${HAIR}`, borderRadius: 12,
  padding: 14, boxShadow: "0 16px 48px rgba(0,0,0,.5)", color: INK,
};

function btn(color: string): React.CSSProperties {
  return {
    font: "inherit", color: INK, background: "var(--panel2, #13283b)",
    border: `1px solid ${color}`, borderRadius: 8, padding: "7px 12px", cursor: "pointer",
  };
}

function chip(color: string): React.CSSProperties {
  return {
    fontSize: 12, padding: "3px 9px", borderRadius: 999,
    border: `1px solid ${color}`, color, background: "transparent",
  };
}

function summaryStyle(agreed: boolean): React.CSSProperties {
  const c = agreed ? "var(--mint, #5eead4)" : "#ff6b5e";
  return {
    marginTop: 10, padding: "8px 10px", borderRadius: 8, fontSize: 12,
    border: `1px solid ${c}`, color: c, background: "rgba(94,234,212,.06)",
  };
}

function intentColor(action: VoiceIntent["action"]): string {
  if (action === "approve") return "var(--mint, #5eead4)";
  if (action === "reject") return "#ff6b5e";
  if (action === "unknown") return INK_DIM;
  return TEAL;
}

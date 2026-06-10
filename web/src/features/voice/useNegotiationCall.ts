import { useCallback, useEffect, useRef, useState } from "react";
import { Player } from "./audio";
import type { CallEventPayload, CallTurn, Speaker } from "./types";

function join(base: string, path: string): string {
  return base.replace(/\/+$/, "") + path;
}

interface CallSummary {
  agreed: boolean;
  lead_time_days?: number;
  quantity?: number;
  unit_price_usd?: number;
  notes?: string;
}

/** In-app two-party negotiation call against the gateway's WS /voice/call. */
export function useNegotiationCall(wsUrl: string) {
  const [active, setActive] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [turns, setTurns] = useState<CallTurn[]>([]);
  const [summary, setSummary] = useState<CallSummary | null>(null);
  const [speaker, setSpeaker] = useState<Speaker | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const playerRef = useRef<Player | null>(null);
  const lastSpeakerRef = useRef<Speaker>("faultline_agent");

  const endCall = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "call.end", call_id: "call-ui" }));
      ws.close();
    }
    wsRef.current = null;
    setActive(false);
    setSpeaker(null);
  }, []);

  const startCall = useCallback(
    (poId = "po-2026-0042") => {
      if (active || !wsUrl) return;
      setTurns([]);
      setSummary(null);
      setStatus("");
      setActive(true);
      if (!playerRef.current) playerRef.current = new Player();

      const callId = "call-ui-" + String(Date.now());
      const ws = new WebSocket(join(wsUrl, "/voice/call"));
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () =>
        ws.send(JSON.stringify({ type: "call.start", call_id: callId, po_id: poId }));

      ws.onmessage = (e: MessageEvent) => {
        if (typeof e.data !== "string") {
          playerRef.current?.push(e.data as ArrayBuffer);
          setSpeaker(lastSpeakerRef.current);
          return;
        }
        const m = JSON.parse(e.data);
        if (m.type === "audio.start") {
          playerRef.current?.ensure(m.sample_rate_hz);
          return;
        }
        if (m.type !== "call.event") return;
        const p = m.payload as CallEventPayload;
        if (p.event === "status") {
          setStatus(p.status || "");
          if (p.status === "ended" || p.status === "failed") setActive(false);
        } else if (p.event === "transcript" && p.speaker && p.text) {
          lastSpeakerRef.current = p.speaker;
          setTurns((t) => [...t, { speaker: p.speaker as Speaker, text: p.text as string }]);
        } else if (p.event === "summary" && p.summary) {
          setSummary(p.summary as CallSummary);
        }
      };
      ws.onclose = () => setActive(false);
      ws.onerror = () => setActive(false);
    },
    [active, wsUrl],
  );

  // Drop the speaking indicator when playback drains.
  useEffect(() => {
    if (!speaker) return;
    const id = setInterval(() => {
      if (!playerRef.current?.speaking) setSpeaker(null);
    }, 200);
    return () => clearInterval(id);
  }, [speaker]);

  useEffect(() => () => {
    wsRef.current?.close();
    playerRef.current?.close();
  }, []);

  return {
    active,
    status,
    turns,
    summary,
    speaker,
    startCall,
    endCall,
    analyser: () => playerRef.current?.analyser ?? null,
  };
}

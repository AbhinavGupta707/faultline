import { useCallback, useEffect, useRef, useState } from "react";
import { Player, Recorder } from "./audio";
import type { VoiceIntent } from "./types";

function join(base: string, path: string): string {
  return base.replace(/\/+$/, "") + path;
}

/** Push-to-talk voice-in against the gateway's WS /voice/intent. */
export function useVoiceIntent(wsUrl: string, onIntent: (i: VoiceIntent) => void) {
  const [recording, setRecording] = useState(false);
  const [partial, setPartial] = useState("");
  const [lastIntent, setLastIntent] = useState<VoiceIntent | null>(null);
  const [ackSpeaking, setAckSpeaking] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const recRef = useRef<Recorder | null>(null);
  const playerRef = useRef<Player | null>(null);
  const onIntentRef = useRef(onIntent);
  onIntentRef.current = onIntent;

  const stopTalking = useCallback(() => {
    setRecording(false);
    recRef.current?.stop();
    recRef.current = null;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
  }, []);

  const startTalking = useCallback(
    async (pendingApprovalId?: string) => {
      if (recording || !wsUrl) return;
      setRecording(true);
      setPartial("");
      if (!playerRef.current) playerRef.current = new Player();

      const ws = new WebSocket(join(wsUrl, "/voice/intent"));
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onmessage = (e: MessageEvent) => {
        if (typeof e.data !== "string") {
          playerRef.current?.push(e.data as ArrayBuffer);
          setAckSpeaking(true);
          return;
        }
        const m = JSON.parse(e.data);
        if (m.type === "transcript.partial") setPartial(m.text);
        else if (m.type === "transcript.final") setPartial(m.text);
        else if (m.type === "audio.start") playerRef.current?.ensure(m.sample_rate_hz);
        else if (m.type === "intent") {
          setLastIntent(m.intent as VoiceIntent);
          onIntentRef.current(m.intent as VoiceIntent);
        }
      };
      ws.onerror = () => stopTalking();

      await new Promise<void>((resolve) => {
        if (ws.readyState === WebSocket.OPEN) resolve();
        else ws.onopen = () => resolve();
      });
      ws.send(
        JSON.stringify({
          type: "start",
          sample_rate_hz: 16000,
          encoding: "pcm16",
          pending_approval_id: pendingApprovalId || undefined,
        }),
      );

      try {
        const rec = new Recorder();
        recRef.current = rec;
        await rec.start((pcm) => {
          if (ws.readyState === WebSocket.OPEN) ws.send(pcm);
        });
      } catch {
        // No mic / permission denied: the gateway still returns an intent in mock mode.
      }
    },
    [recording, wsUrl, stopTalking],
  );

  // Clear the amber "AI speaking" indicator once playback drains.
  useEffect(() => {
    if (!ackSpeaking) return;
    const id = setInterval(() => {
      if (!playerRef.current?.speaking) setAckSpeaking(false);
    }, 200);
    return () => clearInterval(id);
  }, [ackSpeaking]);

  useEffect(() => () => {
    recRef.current?.stop();
    wsRef.current?.close();
    playerRef.current?.close();
  }, []);

  return { recording, partial, lastIntent, ackSpeaking, startTalking, stopTalking };
}

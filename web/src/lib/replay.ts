/** Replay event stream (VITE_DEMO_MODE=replay or ?demo=replay) — drives the entire UI
 *  from contracts/fixtures/ws_replay.jsonl with realistic pacing (sleeps the ts deltas).
 *  Session C1 implements pause-at-approval choreography; this stub plays s2c lines through. */
import replayRaw from "../../../contracts/fixtures/ws_replay.jsonl?raw";
import type { EventStream, StreamHandler, WsMessage } from "./types";

export function loadReplayMessages(): WsMessage[] {
  return replayRaw
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as WsMessage);
}

export function createReplayStream(): EventStream {
  const handlers = new Set<StreamHandler>();
  const messages = loadReplayMessages();
  let stopped = false;

  (async () => {
    let prev: number | null = null;
    for (const msg of messages) {
      if (stopped) return;
      const t = Date.parse(msg.ts);
      if (prev !== null) await new Promise((r) => setTimeout(r, Math.min(t - prev, 10_000)));
      prev = t;
      if (msg.dir === "c2s") continue; // choreography line — C1 wires the approval pause
      handlers.forEach((h) => h(msg));
    }
  })();

  return {
    subscribe(handler) {
      handlers.add(handler);
      return () => {
        handlers.delete(handler);
        if (handlers.size === 0) stopped = true;
      };
    },
    send() {
      /* replay mode: client messages are no-ops (approval handled by choreography) */
    },
  };
}

/** Replay event stream (VITE_DEMO_MODE=replay or ?demo=replay) — drives the entire UI
 *  from contracts/fixtures/ws_replay.jsonl with realistic pacing (sleeps the ts deltas).
 *
 *  Choreography (per ws_protocol.md): the scripted `dir:"c2s"` approval.decision line is a
 *  GATE, not a delivered message. The harness pauses the run at `approval.request` until
 *  either (a) the operator clicks Approve — `send({type:"approval.decision", ...})` — or
 *  (b) an auto-advance timer fires (so the hands-off `?demo=replay` screenshot path still
 *  completes). Same EventStream interface as lib/ws.ts so panels never know the mode.
 *
 *  Swapping to the live socket is one env var (VITE_DEMO_MODE=live) — see lib/stream.ts. */
import replayRaw from "../../../contracts/fixtures/ws_replay.jsonl?raw";
import type { EventStream, StreamHandler, WsMessage } from "./types";

const MAX_DELTA_MS = 6_000; // clamp long scripted gaps so the demo never stalls

export function loadReplayMessages(): WsMessage[] {
  return replayRaw
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as WsMessage);
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, Math.max(0, ms)));

export interface ReplayOptions {
  /** ms to wait at an unattended approval gate before auto-advancing (default 9s). */
  autoApproveAfterMs?: number;
  /** speed multiplier for ts deltas (1 = script pacing). */
  speed?: number;
}

/** ?pace=0.6 slows the replay to narration speed for video recording (1 = scripted pace). */
function urlPace(): number {
  try {
    const p = parseFloat(new URLSearchParams(window.location.search).get("pace") ?? "");
    if (Number.isFinite(p) && p >= 0.3 && p <= 2) return p;
  } catch {
    /* no window — default */
  }
  return 1;
}

export function createReplayStream(opts: ReplayOptions = {}): EventStream {
  const handlers = new Set<StreamHandler>();
  const log: WsMessage[] = []; // delivered s2c history — replayed to late subscribers
  const messages = loadReplayMessages();
  const speed = opts.speed ?? urlPace();
  let stopped = false;

  const deliver = (msg: WsMessage) => {
    log.push(msg);
    handlers.forEach((h) => h(msg));
  };

  // approval gate plumbing
  let resolveGate: (() => void) | null = null;
  const armGate = () =>
    new Promise<void>((resolve) => {
      resolveGate = resolve;
    });

  (async () => {
    let prev: number | null = null;
    for (const msg of messages) {
      if (stopped) return;
      const t = Date.parse(msg.ts);
      const delta = prev === null ? 0 : Math.min((t - prev) / speed, MAX_DELTA_MS);

      if (msg.dir === "c2s") {
        // GATE: wait for the operator's decision, or auto-advance after the timeout.
        const gate = armGate();
        const auto = opts.autoApproveAfterMs ?? Math.max(delta, 9_000 / speed);
        await Promise.race([gate, sleep(auto)]);
        resolveGate = null;
        prev = t; // re-baseline pacing to the scripted decision moment
        continue; // c2s lines are never delivered to handlers (client→server)
      }

      if (delta > 0) await sleep(delta);
      prev = t;
      if (stopped) return;
      deliver(msg);
    }
  })();

  return {
    subscribe(handler) {
      // catch the new subscriber up to the current state, then stream live
      for (const m of log) handler(m);
      handlers.add(handler);
      // NOTE: unsubscribing never stops the run. The replay is a singleton that buffers
      // into `log`, so transient unsubscribes (React StrictMode double-effects, panel
      // remounts) must not kill the loop — late/re-subscribers replay the backlog.
      return () => {
        handlers.delete(handler);
      };
    },
    send(msg) {
      // In replay mode the only meaningful client message is the approval decision,
      // which releases the gate. whatif/chat/voice are no-ops against the fixture.
      if (msg.type === "approval.decision" && resolveGate) resolveGate();
    },
  };
}

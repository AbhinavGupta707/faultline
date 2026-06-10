/** Stream selector — the one switch between replay and live (contracts/components.md §4).
 *  Panels call getEventStream(); they never know which mode they are in. */
import type { EventStream } from "./types";
import { createLiveStream } from "./ws";
import { createReplayStream } from "./replay";

let stream: EventStream | null = null;

export function getEventStream(): EventStream {
  if (!stream) {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get("demo") ?? import.meta.env.VITE_DEMO_MODE ?? "replay";
    stream =
      mode === "live"
        ? createLiveStream(import.meta.env.VITE_WS_URL ?? "ws://localhost:8080/ws")
        : createReplayStream();
  }
  return stream;
}

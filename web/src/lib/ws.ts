/** Live WebSocket event stream (VITE_DEMO_MODE=live) — Session C1 implements
 *  (reconnect/backoff, send queue). Phase 0 stub satisfies the EventStream interface. */
import type { EventStream, StreamHandler, WsMessage } from "./types";

export function createLiveStream(wsUrl: string): EventStream {
  const handlers = new Set<StreamHandler>();
  let socket: WebSocket | null = null;
  try {
    socket = new WebSocket(wsUrl);
    socket.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as WsMessage;
      handlers.forEach((h) => h(msg));
    };
  } catch {
    console.warn("[faultline] live WS unavailable (phase0 stub)");
  }
  return {
    subscribe(handler) {
      handlers.add(handler);
      return () => handlers.delete(handler);
    },
    send(msg) {
      socket?.readyState === WebSocket.OPEN && socket.send(JSON.stringify(msg));
    },
  };
}

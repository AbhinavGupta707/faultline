/** Live WebSocket event stream (VITE_DEMO_MODE=live) — Session C1 owns.
 *  Reconnect with backoff, a send queue for messages issued while disconnected, and a
 *  backlog buffer so panels that subscribe late catch up to the current run state.
 *  Exposes the IDENTICAL EventStream interface as lib/replay.ts — flipping replay→live
 *  is one env var (lib/stream.ts); consumers never know which mode they are in. */
import type { EventStream, StreamHandler, WsMessage } from "./types";

const MAX_BACKLOG = 2000;
const MAX_BACKOFF_MS = 10_000;

export function createLiveStream(wsUrl: string): EventStream {
  const handlers = new Set<StreamHandler>();
  const log: WsMessage[] = [];
  const sendQueue: string[] = [];
  let socket: WebSocket | null = null;
  let backoff = 500;
  let closed = false;

  const deliver = (msg: WsMessage) => {
    if (msg.dir === "c2s") return;
    log.push(msg);
    if (log.length > MAX_BACKLOG) log.shift();
    handlers.forEach((h) => h(msg));
  };

  const connect = () => {
    if (closed) return;
    try {
      socket = new WebSocket(wsUrl);
    } catch {
      scheduleReconnect();
      return;
    }
    socket.onopen = () => {
      backoff = 500;
      while (sendQueue.length && socket?.readyState === WebSocket.OPEN) {
        socket.send(sendQueue.shift()!);
      }
    };
    socket.onmessage = (ev) => {
      try {
        deliver(JSON.parse(ev.data) as WsMessage);
      } catch {
        /* ignore malformed frame */
      }
    };
    socket.onclose = () => scheduleReconnect();
    socket.onerror = () => socket?.close();
  };

  const scheduleReconnect = () => {
    if (closed) return;
    socket = null;
    setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
  };

  connect();

  return {
    subscribe(handler) {
      for (const m of log) handler(m);
      handlers.add(handler);
      // Singleton stream: a transient unsubscribe (StrictMode double-effect, remount)
      // must not tear down the socket. The connection lives for the app session.
      return () => {
        handlers.delete(handler);
      };
    },
    send(msg) {
      const data = JSON.stringify(msg);
      if (socket?.readyState === WebSocket.OPEN) socket.send(data);
      else sendQueue.push(data);
    },
  };
}

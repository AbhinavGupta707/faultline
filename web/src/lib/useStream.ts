/** React bindings over the EventStream (Session C1 owns; panels may import read-only).
 *  `useEventStream` accumulates every server→client message and exposes `send` for
 *  client→server messages (approval.decision, whatif.run, chat, voice.intent). */
import { useEffect, useRef, useState } from "react";
import type { EventStream, WsMessage } from "./types";
import { getEventStream } from "./stream";

export interface StreamApi {
  messages: WsMessage[];
  send: EventStream["send"];
}

export function useEventStream(): StreamApi {
  const [messages, setMessages] = useState<WsMessage[]>([]);
  const streamRef = useRef<EventStream | null>(null);
  if (streamRef.current === null) streamRef.current = getEventStream();

  useEffect(() => {
    const stream = streamRef.current!;
    const unsub = stream.subscribe((msg) => {
      // ignore client-echo / choreography lines defensively
      if (msg.dir === "c2s") return;
      setMessages((prev) => [...prev, msg]);
    });
    return unsub;
  }, []);

  return { messages, send: (m) => streamRef.current?.send(m) };
}

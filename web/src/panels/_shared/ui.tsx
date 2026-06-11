/** Small presentational primitives shared by the C2 panels. */
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ExposureStatus, RelevantEvent } from "./store";
import { hhmm, sourceLabel } from "./format";
import { prefersReducedMotion } from "./anim";
import { focusOnMap, isModifiedClick } from "./focus";

export function Panel({
  title,
  meta,
  children,
  style,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <section className="fl-panel" style={style}>
      <div className="fl-panel__head">
        <span className="fl-panel__title">{title}</span>
        {meta != null && <span className="fl-panel__meta">{meta}</span>}
      </div>
      <div className="fl-panel__body">{children}</div>
    </section>
  );
}

export function StatusPill({ status }: { status: ExposureStatus }) {
  const label = status === "at_risk" ? "At risk" : status === "watch" ? "Watch" : "Secured";
  const prev = useRef(status);
  const [pulse, setPulse] = useState(false);
  useEffect(() => {
    if (prev.current === status) return;
    prev.current = status;
    if (prefersReducedMotion()) return;
    setPulse(true);
    const id = setTimeout(() => setPulse(false), 900);
    return () => clearTimeout(id);
  }, [status]);
  return (
    <span className={`fl-pill fl-pill--${status} ${pulse ? "fl-pill--pulse" : ""}`}>
      <span className={`fl-dot fl-dot--${status}`} />
      {label}
    </span>
  );
}

/** Evidence chip that cites a source world-event: "GDACS · 08:42". Clicking flies
 *  C1's map to the event location; a modified/middle click opens the source URL.
 *  (Decision-log requirement — every conclusion links to live evidence.) */
export function EvidenceChip({ eventId, event }: { eventId: string; event?: RelevantEvent }) {
  const label = event ? `${sourceLabel(event.source)} · ${hhmm(event.published_at)}` : eventId;
  const canFocus = !!event?.location;

  if (canFocus && event) {
    const title = `${event.title} — click to show on map`;
    return (
      <a
        className="fl-chip fl-chip--focus"
        href={event.url ?? "#"}
        target="_blank"
        rel="noreferrer"
        title={title}
        onClick={(e) => {
          if (isModifiedClick(e)) return; // let the browser open the source
          e.preventDefault();
          focusOnMap({
            lat: event.location.lat,
            lon: event.location.lon,
            label: event.place_name || event.title,
            url: event.url,
          });
        }}
      >
        <span className="fl-chip__dot" />
        {label}
      </a>
    );
  }

  if (event?.url) {
    return (
      <a className="fl-chip" href={event.url} target="_blank" rel="noreferrer" title={event.title}>
        <span className="fl-chip__dot" />
        {label}
      </a>
    );
  }
  return (
    <span className="fl-chip" title={event ? event.title : eventId}>
      <span className="fl-chip__dot" />
      {label}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="fl-empty">{children}</div>;
}

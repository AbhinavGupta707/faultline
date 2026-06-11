/** Ripple labels (Session C1 owns) — a self-explaining pill attached to every active
 *  disruption ripple ("Vadodara flood · GDACS", "Cameron Parish storm · NOAA"), so the
 *  red rings read on their own. Rendered as DOM projected from the live deck viewport
 *  (deck TextLayer doesn't render under GlobeView); back-of-globe ripples are culled. */
import { useMemo } from "react";
import type { View } from "@deck.gl/core";
import type { MapState } from "../../lib/mapModel";

const D2R = Math.PI / 180;
function angDeg(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const dLat = (lat2 - lat1) * D2R;
  const dLon = (lon2 - lon1) * D2R;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * D2R) * Math.cos(lat2 * D2R) * Math.sin(dLon / 2) ** 2;
  return (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))) / D2R;
}

export interface RippleLabelsProps {
  state: MapState;
  view: View;
  viewState: Record<string, number>;
  size: { w: number; h: number };
  kind: "globe" | "flat";
}

export default function RippleLabels({ state, view, viewState, size, kind }: RippleLabelsProps) {
  const viewport = useMemo(() => {
    if (size.w === 0) return null;
    try {
      return view.makeViewport({ width: size.w, height: size.h, viewState });
    } catch {
      return null;
    }
  }, [view, size.w, size.h, viewState]);

  if (!viewport || !state.ripples.length) return null;
  const cLon = viewState.longitude ?? 0;
  const cLat = viewState.latitude ?? 0;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}>
      {state.ripples.map((r) => {
        if (kind === "globe" && angDeg(r.lon, r.lat, cLon, cLat) > 84) return null;
        const [x, y] = viewport.project([r.lon, r.lat]) as [number, number];
        if (x < -30 || y < -30 || x > size.w + 30 || y > size.h + 30) return null;
        const color = r.simulated ? "var(--watch)" : "var(--risk)";
        const place = r.placeName.split(",")[0];
        const src = r.source ? ` · ${r.source.toUpperCase()}` : "";
        return (
          <div
            key={r.eventId}
            className="mono"
            style={{
              position: "absolute",
              left: x,
              top: y,
              transform: "translate(-50%, -210%)",
              padding: "3px 8px",
              fontSize: 10.5,
              letterSpacing: "0.02em",
              color: "var(--ink)",
              background: "rgba(6,13,23,0.9)",
              border: `1px solid ${color}`,
              borderRadius: 5,
              whiteSpace: "nowrap",
              boxShadow: `0 0 10px ${color}55`,
            }}
          >
            <span style={{ color }}>{place}</span> {r.eventType}
            <span className="dim">{src}</span>
          </div>
        );
      })}
    </div>
  );
}

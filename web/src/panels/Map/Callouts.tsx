/** Map narration callouts (Session C1 owns) — anchored cards driven by the semantic
 *  stream: event detected (coral), exposure traced (teal), approval pending (amber,
 *  pulsing, persistent), re-source secured (mint). Max 2 concurrent, auto-dismiss,
 *  reduced-motion safe (CSS pulse is disabled by the prefers-reduced-motion guard).
 *  Anchors are projected to screen each frame via the active deck.gl viewport, so they
 *  track the camera as it rotates/flies; back-of-globe anchors are culled. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { View } from "@deck.gl/core";
import type { MapState } from "../../lib/mapModel";
import { EDGES, nodeById } from "../../lib/map/network";

type Tone = "coral" | "teal" | "amber" | "mint";
interface Callout {
  id: string;
  kind: "detected" | "traced" | "approval" | "secured";
  tone: Tone;
  icon: string;
  text: string;
  sub?: string;
  lon: number;
  lat: number;
  createdAt: number;
  ttl: number; // ms; 0 = persistent
  pulse?: boolean;
}

const MAX = 2;
const TONE: Record<Tone, string> = {
  coral: "var(--risk)",
  teal: "var(--graph-edge)",
  amber: "var(--watch)",
  mint: "var(--secured)",
};
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const now = () => Date.now();

const toRad = (d: number) => (d * Math.PI) / 180;
function angularDist(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) * 180) / Math.PI;
}

/** the disruption chokepoint = source supplier of a hot exposure edge */
function chokepoint(state: MapState): { lon: number; lat: number } | null {
  for (const e of EDGES) {
    if (state.hotEdgeKeys.has(`${e.src}>${e.dst}`)) {
      const n = nodeById(e.src);
      if (n) return { lon: n.lon, lat: n.lat };
    }
  }
  return null;
}

function capList(list: Callout[]): Callout[] {
  const out = [...list];
  while (out.length > MAX) {
    const i = out.findIndex((c) => c.ttl > 0); // drop the oldest dismissible one
    if (i === -1) break;
    out.splice(i, 1);
  }
  return out.slice(-MAX);
}

export interface CalloutsProps {
  state: MapState;
  view: View;
  viewState: Record<string, number>;
  size: { w: number; h: number };
  kind: "globe" | "flat";
}

export default function Callouts({ state, view, viewState, size, kind }: CalloutsProps) {
  const [items, setItems] = useState<Callout[]>([]);
  const seen = useRef<Set<string>>(new Set());

  const push = (c: Omit<Callout, "createdAt">) =>
    setItems((prev) => capList([...prev.filter((x) => x.id !== c.id), { ...c, createdAt: now() }]));

  // event detected
  useEffect(() => {
    for (const r of state.ripples) {
      const id = `det-${r.eventId}`;
      if (seen.current.has(id)) continue;
      seen.current.add(id);
      push({
        id,
        kind: "detected",
        tone: r.simulated ? "amber" : "coral",
        icon: "⚠",
        text: `${cap(r.eventType)} detected`,
        sub: r.placeName.split(",")[0],
        lon: r.lon,
        lat: r.lat,
        ttl: 7000,
      });
    }
  }, [state.ripples]);

  // exposure traced
  useEffect(() => {
    const products = Object.keys(state.exposureByProduct);
    if (!products.length || state.hotEdgeKeys.size === 0 || seen.current.has("traced")) return;
    seen.current.add("traced");
    const atRisk = products.filter((p) => state.exposureByProduct[p].status !== "secured");
    const dollars = Object.values(state.exposureByProduct).reduce((a, e) => a + e.dollarsAtRisk, 0);
    const anchor = chokepoint(state) ?? { lon: state.focus?.lon ?? 0, lat: state.focus?.lat ?? 0 };
    push({
      id: "traced",
      kind: "traced",
      tone: "teal",
      icon: "◇",
      text: `${atRisk.length} product${atRisk.length === 1 ? "" : "s"} exposed`,
      sub: dollars > 0 ? `$${Math.round(dollars / 1000)}k at risk` : "tracing supply paths",
      lon: anchor.lon,
      lat: anchor.lat,
      ttl: 8000,
    });
  }, [state.exposureByProduct, state.hotEdgeKeys, state.focus]);

  // re-source secured
  useEffect(() => {
    const sec = state.lastSecured;
    if (!sec || seen.current.has(`sec-${sec.productId}`)) return;
    seen.current.add(`sec-${sec.productId}`);
    const supplier = nodeById(state.recommended ?? "");
    const anchor = supplier ?? chokepoint(state) ?? { lon: state.focus?.lon ?? 0, lat: state.focus?.lat ?? 0 };
    const beats =
      sec.leadDays != null && sec.coverDays != null
        ? `${sec.leadDays}d lead beats ${sec.coverDays}d runway`
        : "coverage gap closed";
    push({
      id: `sec-${sec.productId}`,
      kind: "secured",
      tone: "mint",
      icon: "✓",
      text: `Re-sourced · ${sec.supplierName.split(" ").slice(0, 2).join(" ")}`,
      sub: beats,
      lon: anchor.lon,
      lat: anchor.lat,
      ttl: 9000,
    });
  }, [state.lastSecured, state.recommended]);

  // approval pending — persistent + pulsing while the gate is open
  useEffect(() => {
    setItems((prev) => {
      const without = prev.filter((c) => c.kind !== "approval");
      if (!state.approvalPending) return without;
      const anchor = chokepoint(state) ?? { lon: state.focus?.lon ?? 0, lat: state.focus?.lat ?? 0 };
      return capList([
        ...without,
        {
          id: "approval",
          kind: "approval",
          tone: "amber",
          icon: "⏳",
          text: "Approval required",
          sub: "re-source the emulsifier supply",
          lon: anchor.lon,
          lat: anchor.lat,
          createdAt: now(),
          ttl: 0,
          pulse: true,
        },
      ]);
    });
  }, [state.approvalPending]);

  // prune expired (dismissible) callouts
  useEffect(() => {
    const t = setInterval(() => {
      setItems((prev) => prev.filter((c) => c.ttl === 0 || now() - c.createdAt < c.ttl));
    }, 500);
    return () => clearInterval(t);
  }, []);

  const viewport = useMemo(() => {
    if (size.w === 0) return null;
    try {
      return view.makeViewport({ width: size.w, height: size.h, viewState });
    } catch {
      return null;
    }
  }, [view, size.w, size.h, viewState]);

  if (!viewport) return null;
  const centerLon = viewState.longitude ?? 0;
  const centerLat = viewState.latitude ?? 0;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}>
      {items.map((c) => {
        if (kind === "globe" && angularDist(c.lon, c.lat, centerLon, centerLat) > 82) return null;
        const [x, y] = viewport.project([c.lon, c.lat]) as [number, number];
        if (x < -40 || y < -40 || x > size.w + 40 || y > size.h + 40) return null;
        const color = TONE[c.tone];
        return (
          <div
            key={c.id}
            className="fade-up"
            style={{
              position: "absolute",
              left: x,
              top: y,
              transform: "translate(-50%, calc(-100% - 14px))",
              maxWidth: 230,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                padding: "7px 11px",
                background: "rgba(6,13,23,0.92)",
                border: `1px solid ${color}`,
                borderLeft: `3px solid ${color}`,
                borderRadius: 7,
                boxShadow: `0 4px 18px rgba(0,0,0,0.5), 0 0 14px ${color}40`,
                backdropFilter: "blur(3px)",
                animation: c.pulse ? "fl-pulse 1.6s ease-in-out infinite" : undefined,
              }}
            >
              <span style={{ color, fontSize: 13, lineHeight: 1 }}>{c.icon}</span>
              <span style={{ lineHeight: 1.25 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink)", display: "block", letterSpacing: "0.01em" }}>
                  {c.text}
                </span>
                {c.sub && (
                  <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-dim)" }}>
                    {c.sub}
                  </span>
                )}
              </span>
            </div>
            {/* little stem down to the anchor */}
            <div style={{ width: 1, height: 12, background: color, margin: "0 auto", opacity: 0.6 }} />
          </div>
        );
      })}
    </div>
  );
}

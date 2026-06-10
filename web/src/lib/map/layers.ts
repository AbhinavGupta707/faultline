/** Living-map layer builder (Session C1 owns — THE hero).
 *  Pure function: (MapState, time, reducedMotion) → deck.gl Layer[]. Every visual is
 *  derived from the semantic stream via mapModel; nothing here talks to the network. */
import { ArcLayer, GeoJsonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { EDGES, NODES, nodeById, pos, edgeKey } from "./network";
import { getWorldLand } from "./worldGeo";
import type { MapState } from "../mapModel";

type RGBA = [number, number, number, number];
const TEAL = [45, 212, 191] as const;
const CORAL = [255, 92, 92] as const;
const AMBER = [245, 181, 68] as const;
const MINT = [74, 222, 128] as const;
const INK_DIM = [138, 155, 179] as const;
const rgba = (c: readonly number[], a: number): RGBA => [c[0], c[1], c[2], a];

// smooth 0..1 triangle/ease helpers
const fract = (x: number) => x - Math.floor(x);
const pulse = (t: number, period: number) => 0.5 + 0.5 * Math.sin((t / period) * Math.PI * 2);

export interface RippleDatum {
  position: [number, number];
  radius: number; // meters
  color: RGBA;
  width: number; // px
}

/** Expanding concentric rings at each disruption (coral) and the agent scan (gold). */
function ripplesData(state: MapState, time: number, reduced: boolean): RippleDatum[] {
  const out: RippleDatum[] = [];
  const RINGS = 3;
  for (const r of state.ripples) {
    const intensity = 0.5 + 0.5 * r.severity;
    const maxR = 350_000 + r.severity * 700_000; // 350–1050 km
    const base = r.simulated ? AMBER : CORAL;
    const period = 3.0;
    for (let k = 0; k < RINGS; k++) {
      const f = reduced ? (k + 1) / (RINGS + 1) : fract(time / period + k / RINGS);
      out.push({
        position: [r.lon, r.lat],
        radius: 60_000 + f * maxR,
        color: rgba(base, Math.round((1 - f) * (reduced ? 130 : 210) * intensity)),
        width: 2.4,
      });
    }
  }
  // gold scan-pulse at the agent's current focus
  if (state.focus) {
    const period = 2.4;
    for (let k = 0; k < 2; k++) {
      const f = reduced ? 0.45 + k * 0.25 : fract(time / period + k / 2);
      out.push({
        position: [state.focus.lon, state.focus.lat],
        radius: 40_000 + f * 520_000,
        color: rgba(AMBER, Math.round((1 - f) * (reduced ? 120 : 200))),
        width: 2.0,
      });
    }
  }
  return out;
}

function nodeColor(state: MapState, id: string, kind: string): RGBA {
  if (kind === "product") {
    if (state.secured.has(id)) return rgba(MINT, 255);
    const ex = state.exposureByProduct[id];
    if (ex?.status === "at_risk") return rgba(CORAL, 255);
    if (ex?.status === "watch") return rgba(AMBER, 255);
    return rgba(INK_DIM, 200);
  }
  // supplier
  if (state.recommended === id) return rgba(AMBER, 255);
  if (state.altCandidates.has(id)) return rgba(AMBER, 170);
  // disrupted chokepoint = source of a hot exposure edge
  const isChoke = EDGES.some((e) => state.hotEdgeKeys.has(edgeKey(e.src, e.dst)) && e.src === id);
  if (isChoke) return rgba(CORAL, 235);
  return rgba(TEAL, 150);
}

function nodeRadius(state: MapState, id: string, kind: string, time: number, reduced: boolean): number {
  if (kind === "product") {
    const ex = state.exposureByProduct[id];
    const hot = ex && ex.status !== "secured" && !state.secured.has(id);
    const breathe = reduced ? 1 : 0.85 + 0.3 * pulse(time, hot ? 1.4 : 3.0);
    return (hot ? 9 : 7) * breathe;
  }
  if (state.recommended === id) return reduced ? 8 : 7 + 2.5 * pulse(time, 1.6);
  return 4.5;
}

export interface LabelDatum {
  position: [number, number];
  text: string;
  color: RGBA;
  size: number;
}

function labelsData(state: MapState): LabelDatum[] {
  const out: LabelDatum[] = [];
  // product labels (always) — name + cover/secured
  for (const n of NODES) {
    if (n.kind !== "product") continue;
    const ex = state.exposureByProduct[n.id];
    let sub = "";
    let color: RGBA = rgba(INK_DIM, 230);
    if (state.secured.has(n.id)) {
      sub = " · secured";
      color = rgba(MINT, 255);
    } else if (ex) {
      sub = ` · ${ex.daysOfCover}d cover`;
      color = ex.status === "at_risk" ? rgba(CORAL, 255) : rgba(AMBER, 255);
    }
    out.push({ position: [n.lon, n.lat], text: `${n.short}${sub}`, color, size: 12 });
  }
  // chokepoint + recommended supplier labels
  const important = new Set<string>();
  for (const e of EDGES) if (state.hotEdgeKeys.has(edgeKey(e.src, e.dst))) important.add(e.src);
  if (state.recommended) important.add(state.recommended);
  for (const id of important) {
    const n = nodeById(id);
    if (!n || n.kind !== "supplier") continue;
    const recommended = state.recommended === id;
    out.push({
      position: [n.lon, n.lat],
      text: n.short,
      color: recommended ? rgba(AMBER, 255) : rgba(CORAL, 235),
      size: 11,
    });
  }
  // event place labels
  for (const r of state.ripples) {
    out.push({
      position: [r.lon, r.lat],
      text: r.placeName.split(",")[0],
      color: rgba(r.simulated ? AMBER : CORAL, 235),
      size: 11,
    });
  }
  return out;
}

export function buildLayers(state: MapState, time: number, reduced: boolean): Layer[] {
  const edgeData = EDGES.map((e) => {
    const from = pos(e.src);
    const to = pos(e.dst);
    const hot = state.hotEdgeKeys.has(edgeKey(e.src, e.dst));
    return from && to ? { ...e, from, to, hot } : null;
  }).filter(Boolean) as Array<{ from: [number, number]; to: [number, number]; hot: boolean; id: string }>;

  const hotAlpha = reduced ? 220 : Math.round(150 + 105 * pulse(time, 1.3));
  const ripples = ripplesData(state, time, reduced);
  const labels = labelsData(state);

  const land = new GeoJsonLayer({
    id: "world-land",
    data: getWorldLand(),
    filled: true,
    stroked: true,
    getFillColor: [27, 42, 61, 255],
    getLineColor: [86, 116, 152, 70],
    lineWidthMinPixels: 0.7,
    parameters: { depthTest: false },
  });

  // soft teal "bloom" pass under the arcs (wide + translucent)
  const arcBloom = new ArcLayer({
    id: "arc-bloom",
    data: edgeData,
    greatCircle: true,
    getSourcePosition: (d: any) => d.from,
    getTargetPosition: (d: any) => d.to,
    getSourceColor: (d: any) => (d.hot ? rgba(CORAL, 60) : rgba(TEAL, 26)),
    getTargetColor: (d: any) => (d.hot ? rgba(CORAL, 40) : rgba(TEAL, 20)),
    getWidth: (d: any) => (d.hot ? 9 : 6),
    getHeight: 0.5,
    widthUnits: "pixels",
    parameters: { depthTest: false },
  });

  const arcs = new ArcLayer({
    id: "arc-core",
    data: edgeData,
    greatCircle: true,
    getSourcePosition: (d: any) => d.from,
    getTargetPosition: (d: any) => d.to,
    getSourceColor: (d: any) => (d.hot ? rgba(CORAL, hotAlpha) : rgba(TEAL, 150)),
    getTargetColor: (d: any) => (d.hot ? rgba(CORAL, Math.max(120, hotAlpha - 40)) : rgba(TEAL, 90)),
    getWidth: (d: any) => (d.hot ? 2.4 : 1.3),
    getHeight: 0.5,
    widthUnits: "pixels",
    updateTriggers: { getSourceColor: [hotAlpha], getTargetColor: [hotAlpha] },
    parameters: { depthTest: false },
  });

  const rippleLayer = new ScatterplotLayer({
    id: "ripples",
    data: ripples,
    getPosition: (d: RippleDatum) => d.position,
    getRadius: (d: RippleDatum) => d.radius,
    radiusUnits: "meters",
    stroked: true,
    filled: false,
    getLineColor: (d: RippleDatum) => d.color,
    getLineWidth: (d: RippleDatum) => d.width,
    lineWidthUnits: "pixels",
    updateTriggers: { getRadius: [time], getLineColor: [time] },
    parameters: { depthTest: false },
  });

  // node glow halos (filled, low alpha) under the crisp node dots
  const halos = new ScatterplotLayer({
    id: "node-halos",
    data: NODES,
    getPosition: (d: any) => [d.lon, d.lat],
    getRadius: (d: any) => nodeRadius(state, d.id, d.kind, time, reduced) * 2.6,
    radiusUnits: "pixels",
    getFillColor: (d: any) => {
      const c = nodeColor(state, d.id, d.kind);
      return [c[0], c[1], c[2], Math.round(c[3] * 0.16)];
    },
    updateTriggers: { getRadius: [time, state], getFillColor: [state] },
    parameters: { depthTest: false },
  });

  const nodes = new ScatterplotLayer({
    id: "nodes",
    data: NODES,
    getPosition: (d: any) => [d.lon, d.lat],
    getRadius: (d: any) => nodeRadius(state, d.id, d.kind, time, reduced),
    radiusUnits: "pixels",
    radiusMinPixels: 2,
    stroked: true,
    getLineColor: [10, 20, 34, 255],
    getLineWidth: 1,
    lineWidthUnits: "pixels",
    getFillColor: (d: any) => nodeColor(state, d.id, d.kind),
    updateTriggers: { getRadius: [time, state], getFillColor: [state] },
    parameters: { depthTest: false },
  });

  const text = new TextLayer({
    id: "labels",
    data: labels,
    getPosition: (d: LabelDatum) => d.position,
    getText: (d: LabelDatum) => d.text,
    getColor: (d: LabelDatum) => d.color,
    getSize: (d: LabelDatum) => d.size,
    sizeUnits: "pixels",
    getTextAnchor: "start",
    getAlignmentBaseline: "center",
    getPixelOffset: [10, 0],
    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
    fontWeight: 500,
    outlineColor: [6, 13, 23, 255],
    outlineWidth: 3,
    fontSettings: { sdf: true, buffer: 8 },
    background: false,
    updateTriggers: { getText: [state], getColor: [state] },
    parameters: { depthTest: false },
  });

  return [land, arcBloom, arcs, rippleLayer, halos, nodes, text];
}

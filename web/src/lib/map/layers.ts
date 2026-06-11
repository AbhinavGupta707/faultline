/** Living-map layer builder (Session C1 owns — THE hero).
 *  Pure function: (MapState, time, reducedMotion) → deck.gl Layer[]. Every visual is
 *  derived from the semantic stream via mapModel; nothing here talks to the network. */
import { ArcLayer, GeoJsonLayer, LineLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { SimpleMeshLayer } from "@deck.gl/mesh-layers";
import { CollisionFilterExtension } from "@deck.gl/extensions";
import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { SphereGeometry } from "@luma.gl/engine";
import type { Layer } from "@deck.gl/core";
import { EDGES, NODES, nodeById, pos, edgeKey } from "./network";
import { getWorldLand } from "./worldGeo";
import type { MapState } from "../mapModel";

export type MapViewKind = "globe" | "flat";
const EARTH_RADIUS = 6_371_000;
// one shared sphere mesh for the globe ocean (built lazily, reused across renders)
let sphereMesh: SphereGeometry | null = null;
const getSphere = () =>
  (sphereMesh ??= new SphereGeometry({ radius: EARTH_RADIUS * 0.997, nlat: 36, nlong: 72 }));

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
  position: [number, number]; // where the text pill renders
  text: string;
  color: RGBA;
  size: number;
  priority: number; // collision priority — products/events win over suppliers
  anchor: "start" | "end" | "middle";
  pixelOffset: [number, number];
  leaderFrom?: [number, number]; // node position, for the leader line
}

// product labels are fanned west into the Pacific and leader-lined back to the
// clustered finished-product nodes near Portland — so they never overlap each other.
const PRODUCT_ANCHOR: Record<string, [number, number]> = {
  "prd-granola-bar": [-131, 49.5],
  "prd-sparkling-botanical": [-131, 45.2],
  "prd-coldbrew-12oz": [-131, 40.9],
};

function labelsData(state: MapState, hoveredId: string | null): LabelDatum[] {
  const out: LabelDatum[] = [];

  // products — always shown, leader-lined, highest priority
  for (const n of NODES) {
    if (n.kind !== "product") continue;
    const ex = state.exposureByProduct[n.id];
    let sub = "";
    let color: RGBA = rgba(INK_DIM, 235);
    if (state.secured.has(n.id)) {
      sub = " · secured";
      color = rgba(MINT, 255);
    } else if (ex) {
      sub = ` · ${ex.daysOfCover}d cover`;
      color = ex.status === "at_risk" ? rgba(CORAL, 255) : rgba(AMBER, 255);
    }
    out.push({
      position: PRODUCT_ANCHOR[n.id] ?? [n.lon, n.lat],
      text: `${n.short}${sub}`,
      color,
      size: 12,
      priority: 100,
      anchor: "end",
      pixelOffset: [-8, 0],
      leaderFrom: [n.lon, n.lat],
    });
  }

  // suppliers — only the relevant ones (chokepoint, recommended) or the hovered node
  const important = new Set<string>();
  for (const e of EDGES) if (state.hotEdgeKeys.has(edgeKey(e.src, e.dst))) important.add(e.src);
  if (state.recommended) important.add(state.recommended);
  if (hoveredId) important.add(hoveredId);
  for (const id of important) {
    const n = nodeById(id);
    if (!n || n.kind !== "supplier") continue;
    const recommended = state.recommended === id;
    const hovered = hoveredId === id;
    out.push({
      position: [n.lon, n.lat],
      text: n.short,
      color: recommended ? rgba(AMBER, 255) : hovered ? rgba(INK_DIM, 255) : rgba(CORAL, 235),
      size: 11,
      priority: hovered ? 95 : 70,
      anchor: "start",
      pixelOffset: [12, 0],
    });
  }

  // event place labels
  for (const r of state.ripples) {
    out.push({
      position: [r.lon, r.lat],
      text: r.placeName.split(",")[0],
      color: rgba(r.simulated ? AMBER : CORAL, 235),
      size: 11,
      priority: 88,
      anchor: "start",
      pixelOffset: [12, 0],
    });
  }
  return out;
}

export function buildLayers(
  state: MapState,
  time: number,
  reduced: boolean,
  view: MapViewKind = "flat",
  hoveredId: string | null = null
): Layer[] {
  // On the globe we depth-test so the far hemisphere is occluded by the ocean sphere;
  // on the flat map we disable it so the bloom/ripple passes composite freely.
  const globe = view === "globe";
  const depthTest = globe;
  const edgeData = EDGES.map((e) => {
    const from = pos(e.src);
    const to = pos(e.dst);
    const hot = state.hotEdgeKeys.has(edgeKey(e.src, e.dst));
    return from && to ? { ...e, from, to, hot } : null;
  }).filter(Boolean) as Array<{ from: [number, number]; to: [number, number]; hot: boolean; id: string }>;

  const hotAlpha = reduced ? 220 : Math.round(150 + 105 * pulse(time, 1.3));
  const ripples = ripplesData(state, time, reduced);
  const labels = labelsData(state, hoveredId);
  const leaders = labels.filter((l) => l.leaderFrom);

  const land = new GeoJsonLayer({
    id: "world-land",
    data: getWorldLand(),
    filled: true,
    stroked: true,
    getFillColor: [27, 42, 61, 255],
    getLineColor: [86, 116, 152, 70],
    lineWidthMinPixels: 0.7,
    parameters: { depthTest },
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
    parameters: { depthTest },
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
    parameters: { depthTest },
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
    parameters: { depthTest },
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
    parameters: { depthTest },
  });

  const nodes = new ScatterplotLayer({
    id: "nodes",
    data: NODES,
    pickable: true,
    getPosition: (d: any) => [d.lon, d.lat],
    getRadius: (d: any) => nodeRadius(state, d.id, d.kind, time, reduced),
    radiusUnits: "pixels",
    radiusMinPixels: 2,
    radiusScale: 1,
    stroked: true,
    getLineColor: (d: any) => (hoveredId === d.id ? [230, 237, 246, 255] : [10, 20, 34, 255]),
    getLineWidth: (d: any) => (hoveredId === d.id ? 2 : 1),
    lineWidthUnits: "pixels",
    getFillColor: (d: any) => nodeColor(state, d.id, d.kind),
    updateTriggers: { getRadius: [time, state], getFillColor: [state], getLineColor: [hoveredId], getLineWidth: [hoveredId] },
    parameters: { depthTest },
  });

  // thin leader lines from clustered product nodes out to their fanned labels
  const leaderLines = new LineLayer({
    id: "label-leaders",
    data: leaders,
    getSourcePosition: (d: LabelDatum) => d.leaderFrom!,
    getTargetPosition: (d: LabelDatum) => d.position,
    getColor: [138, 155, 179, 90],
    getWidth: 1,
    widthUnits: "pixels",
    parameters: { depthTest },
  });

  const text = new TextLayer({
    id: "labels",
    data: labels,
    getPosition: (d: LabelDatum) => d.position,
    getText: (d: LabelDatum) => d.text,
    getColor: (d: LabelDatum) => d.color,
    getSize: (d: LabelDatum) => d.size,
    sizeUnits: "pixels",
    getTextAnchor: (d: LabelDatum) => d.anchor,
    getAlignmentBaseline: "center",
    getPixelOffset: (d: LabelDatum) => d.pixelOffset,
    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
    fontWeight: 500,
    fontSettings: { sdf: true, buffer: 8 },
    outlineColor: [6, 13, 23, 255],
    outlineWidth: 2,
    // background pill for legibility over land/arcs
    background: true,
    getBackgroundColor: [6, 13, 23, 215],
    backgroundPadding: [7, 3, 7, 3],
    getBorderColor: [86, 116, 152, 110],
    getBorderWidth: 1,
    // declutter: keep higher-priority labels, drop colliding lower ones
    extensions: [new CollisionFilterExtension()],
    collisionEnabled: true,
    collisionGroup: "labels",
    getCollisionPriority: (d: LabelDatum) => d.priority,
    collisionTestProps: { sizeScale: 1 },
    updateTriggers: {
      getText: [state, hoveredId],
      getColor: [state, hoveredId],
      getPosition: [state, hoveredId],
      getCollisionPriority: [state, hoveredId],
    },
    parameters: { depthTest },
  });

  if (globe) {
    // opaque ocean sphere just under the land — writes depth so the back of the globe
    // (its arcs, nodes, ripples) is correctly hidden.
    const ocean = new SimpleMeshLayer({
      id: "globe-ocean",
      data: [{ position: [0, 0, 0] }],
      mesh: getSphere(),
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getPosition: (d: { position: number[] }) => d.position as [number, number, number],
      getColor: [8, 16, 28],
      parameters: { depthTest: true },
    });
    return [ocean, land, arcBloom, arcs, rippleLayer, halos, leaderLines, nodes, text];
  }

  return [land, arcBloom, arcs, rippleLayer, halos, leaderLines, nodes, text];
}

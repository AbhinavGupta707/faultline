/** Living-map layer builder (Session C1 owns — THE hero).
 *  Pure function: (MapState, time, reducedMotion) → deck.gl Layer[]. Every visual is
 *  derived from the semantic stream via mapModel; nothing here talks to the network. */
import { ArcLayer, GeoJsonLayer, LineLayer, PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { SimpleMeshLayer } from "@deck.gl/mesh-layers";
import { CollisionFilterExtension } from "@deck.gl/extensions";
import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { SphereGeometry } from "@luma.gl/engine";
import type { Layer } from "@deck.gl/core";
import { EDGES, NODES, nodeById, pos, edgeKey } from "./network";
import { getWorldLand } from "./worldGeo";
import type { MapState } from "../mapModel";
import type { AmbientBlip } from "../intel";

export type MapViewKind = "globe" | "flat";
const EARTH_RADIUS = 6_371_000;

const D2R = Math.PI / 180;
/** great-circle angular distance in degrees — used to cull back-of-globe labels */
function angDeg(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const dLat = (lat2 - lat1) * D2R;
  const dLon = (lon2 - lon1) * D2R;
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * D2R) * Math.cos(lat2 * D2R) * Math.sin(dLon / 2) ** 2;
  return (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))) / D2R;
}
/** ArcLayer does not render under GlobeView (its arc interpolation happens in a planar
 *  common space — the geometry ends up inside the sphere and is depth-culled). So on the
 *  globe, supply routes are PathLayers along precomputed great-circle waypoints, lifted
 *  off the surface so they read as flight-lines. Cached per edge — geometry is static. */
const gcCache = new Map<string, [number, number, number][]>();
function gcPath(key: string, from: [number, number], to: [number, number]): [number, number, number][] {
  const hit = gcCache.get(key);
  if (hit) return hit;
  const toV = (lon: number, lat: number) => {
    const p = lat * D2R, l = lon * D2R;
    return [Math.cos(p) * Math.cos(l), Math.cos(p) * Math.sin(l), Math.sin(p)] as const;
  };
  const a = toV(from[0], from[1]);
  const b = toV(to[0], to[1]);
  const dot = Math.min(1, Math.max(-1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  const w = Math.acos(dot) || 1e-6;
  const sw = Math.sin(w);
  // lift scales with arc length: short hops hug the surface, transcontinental routes soar
  const lift = EARTH_RADIUS * (0.012 + 0.085 * (w / Math.PI));
  const N = 48;
  const pts: [number, number, number][] = [];
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    const s1 = Math.sin((1 - t) * w) / sw;
    const s2 = Math.sin(t * w) / sw;
    const x = s1 * a[0] + s2 * b[0];
    const y = s1 * a[1] + s2 * b[1];
    const z = s1 * a[2] + s2 * b[2];
    pts.push([Math.atan2(y, x) / D2R, Math.atan2(z, Math.hypot(x, y)) / D2R, Math.sin(t * Math.PI) * lift]);
  }
  gcCache.set(key, pts);
  return pts;
}

const strHash = (s: string) => {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
};

interface FlowDot {
  position: [number, number, number];
  color: RGBA;
  size: number;
}
/** Energy pulses travel ONLY along routes that matter right now — hot exposure paths
 *  (coral) and the secured re-route via the recommended alternate (mint). The baseline
 *  network stays still: motion is information, not decoration. */
function flowData(
  paths: Array<{ id: string; hot: boolean; secured?: boolean; path: [number, number, number][] }>,
  time: number
): FlowDot[] {
  const out: FlowDot[] = [];
  for (const e of paths) {
    if (!e.hot && !e.secured) continue;
    const n = 3;
    const phase = (strHash(e.id) % 100) / 100;
    for (let k = 0; k < n; k++) {
      const f = fract(time / 2.4 + k / n + phase);
      const idx = f * (e.path.length - 1);
      const i0 = Math.floor(idx);
      const t = idx - i0;
      const p0 = e.path[i0];
      const p1 = e.path[Math.min(i0 + 1, e.path.length - 1)];
      out.push({
        position: [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t, p0[2] + (p1[2] - p0[2]) * t],
        color: e.secured ? rgba(MINT, 230) : rgba(CORAL, 235),
        size: 3.6,
      });
    }
  }
  return out;
}

// one shared sphere mesh for the globe ocean (built lazily, reused across renders)
let sphereMesh: SphereGeometry | null = null;
const getSphere = () =>
  // radius set well below the surface so large land triangles (whose flat chords sag
  // toward the centre on the sphere) never dip beneath the ocean and get depth-occluded
  // into black holes. The ~1.5% limb inset is imperceptible at globe scale.
  (sphereMesh ??= new SphereGeometry({ radius: EARTH_RADIUS * 0.985, nlat: 48, nlong: 96 }));

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

  // (disruption ripple labels are rendered as projected DOM pills — see RippleLabels —
  //  because deck TextLayer doesn't render reliably under GlobeView.)
  return out;
}

export function buildLayers(
  state: MapState,
  time: number,
  reduced: boolean,
  view: MapViewKind = "flat",
  hoveredId: string | null = null,
  ambient: AmbientBlip[] = [],
  center: { lon: number; lat: number } | null = null
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
  let labels = labelsData(state, hoveredId);
  // On the globe, text can't depth-test (it would z-fight the coplanar land and vanish),
  // so we render it always-on-top and cull back-hemisphere labels here by view center.
  if (globe && center) labels = labels.filter((l) => angDeg(l.position[0], l.position[1], center.lon, center.lat) < 86);
  const leaders = labels.filter((l) => l.leaderFrom);

  const land = new GeoJsonLayer({
    id: "world-land",
    data: getWorldLand(),
    filled: true,
    stroked: true,
    // muted earth tones: land reads as land against the deep-water ocean
    getFillColor: [31, 44, 46, 255],
    getLineColor: [98, 126, 108, 75],
    lineWidthMinPixels: 0.7,
    // Globe fill correctness: _full3d uses the 3D tesselator (concave countries fill on
    // the sphere), and cullMode:'none' stops back-face culling from dropping whole
    // countries whose ring winding is reversed in the source topology. Together they
    // eliminate the black holes. (_full3d must be set on the fill sublayer.)
    _subLayerProps: { "polygons-fill": { _full3d: globe } },
    parameters: { depthTest, cullMode: globe ? "none" : undefined },
  });

  // ambient "recent events" field — faint grey breathing blips; Watcher-relevant ones
  // ignite coral (simulated/what-if events read amber). Pure background texture.
  const relevantIds = new Set(state.ripples.map((r) => r.eventId));
  const ambientLayer = new ScatterplotLayer({
    id: "ambient-events",
    data: ambient,
    getPosition: (d: AmbientBlip) => [d.lon, d.lat],
    getRadius: (d: AmbientBlip) => {
      const hot = relevantIds.has(d.id);
      const phase = (d.lon + d.lat) % 3; // stable per-blip phase
      const breathe = reduced ? 1 : 0.7 + 0.5 * pulse(time + phase, hot ? 1.5 : 3.2);
      return (hot ? 4.2 : 2.4) * breathe;
    },
    radiusUnits: "pixels",
    radiusMinPixels: 1.5,
    stroked: false,
    getFillColor: (d: AmbientBlip): RGBA => {
      if (relevantIds.has(d.id)) return rgba(CORAL, 230);
      if (d.simulated) return rgba(AMBER, 200);
      return [138, 155, 179, d.hasHeadline ? 150 : 95];
    },
    updateTriggers: { getRadius: [time, state], getFillColor: [state] },
    parameters: { depthTest },
  });

  // soft teal "bloom" pass under the arcs (wide + translucent)
  const arcBloom = new ArcLayer({
    id: "arc-bloom",
    data: edgeData,
    greatCircle: true,
    getSourcePosition: (d: any) => d.from,
    getTargetPosition: (d: any) => d.to,
    getSourceColor: (d: any) => (d.hot ? rgba(CORAL, 60) : rgba(TEAL, 13)),
    getTargetColor: (d: any) => (d.hot ? rgba(CORAL, 40) : rgba(TEAL, 10)),
    getWidth: (d: any) => (d.hot ? 9 : 4),
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
    getSourceColor: (d: any) => (d.hot ? rgba(CORAL, hotAlpha) : rgba(TEAL, 70)),
    getTargetColor: (d: any) => (d.hot ? rgba(CORAL, Math.max(120, hotAlpha - 40)) : rgba(TEAL, 45)),
    getWidth: (d: any) => (d.hot ? 3.0 : 0.9),
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
    // declutter: keep higher-priority labels, drop colliding lower ones. The collision
    // pass is screen-space and misbehaves under the globe projection (it hides every
    // label), so it's flat-only; on the globe, depth-testing already hides the back side.
    extensions: globe ? [] : [new CollisionFilterExtension()],
    collisionEnabled: !globe,
    collisionGroup: "labels",
    getCollisionPriority: (d: LabelDatum) => d.priority,
    collisionTestProps: { sizeScale: 1 },
    updateTriggers: {
      getText: [state, hoveredId],
      getColor: [state, hoveredId],
      getPosition: [state, hoveredId],
      getCollisionPriority: [state, hoveredId],
    },
    // always-on-top: globe text can't depth-test (coplanar with land); back-side labels
    // are culled by view center above instead.
    parameters: { depthTest: false },
  });

  if (globe) {
    // opaque ocean sphere just under the land — writes depth so the back of the globe
    // (its arcs, nodes, ripples) is correctly hidden. Deep-water blue, not flat black.
    const ocean = new SimpleMeshLayer({
      id: "globe-ocean",
      data: [{ position: [0, 0, 0] }],
      mesh: getSphere(),
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getPosition: (d: { position: number[] }) => d.position as [number, number, number],
      getColor: [12, 27, 48],
      parameters: { depthTest: true },
    });
    // ArcLayer is a no-show under GlobeView → lifted great-circle PathLayers instead.
    // Visual hierarchy: the baseline network is faint context; threatened paths ignite
    // coral and pulse; once re-sourced, a NEW mint route appears from the recommended
    // alternate to each secured product. Show things only when they mean something.
    const pathData = edgeData.map((e) => ({ ...e, secured: false, path: gcPath(e.id, e.from, e.to) }));
    const securedPaths: typeof pathData = [];
    if (state.recommended) {
      const from = pos(state.recommended);
      if (from)
        for (const pid of state.secured) {
          const to = pos(pid);
          if (to) {
            const id = `secured-${state.recommended}-${pid}`;
            securedPaths.push({ id, hot: false, secured: true, from, to, path: gcPath(id, from, to) } as (typeof pathData)[number]);
          }
        }
    }
    const allPaths = pathData.concat(securedPaths);
    const routeBloom = new PathLayer({
      id: "route-bloom",
      data: allPaths,
      getPath: (d: any) => d.path,
      getColor: (d: any) => (d.hot ? rgba(CORAL, 55) : d.secured ? rgba(MINT, 50) : rgba(TEAL, 14)),
      getWidth: (d: any) => (d.hot || d.secured ? 8.5 : 3.5),
      widthUnits: "pixels",
      jointRounded: true,
      updateTriggers: { getColor: [state], getWidth: [state] },
      parameters: { depthTest },
    });
    const routeCore = new PathLayer({
      id: "route-core",
      data: allPaths,
      getPath: (d: any) => d.path,
      getColor: (d: any) => (d.hot ? rgba(CORAL, hotAlpha) : d.secured ? rgba(MINT, 220) : rgba(TEAL, 70)),
      getWidth: (d: any) => (d.hot ? 3.0 : d.secured ? 2.4 : 0.9),
      widthUnits: "pixels",
      jointRounded: true,
      updateTriggers: { getColor: [hotAlpha, state], getWidth: [state] },
      parameters: { depthTest },
    });
    const flow = new ScatterplotLayer({
      id: "route-flow",
      data: reduced ? [] : flowData(allPaths, time),
      getPosition: (d: FlowDot) => d.position,
      getRadius: (d: FlowDot) => d.size,
      radiusUnits: "pixels",
      stroked: false,
      getFillColor: (d: FlowDot) => d.color,
      parameters: { depthTest },
    });
    return [ocean, land, ambientLayer, routeBloom, routeCore, flow, rippleLayer, halos, leaderLines, nodes, text];
  }

  return [land, ambientLayer, arcBloom, arcs, rippleLayer, halos, leaderLines, nodes, text];
}

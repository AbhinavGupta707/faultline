/** The living map — THE hero (Session C1 owns).
 *  deck.gl world map: teal supplier-graph arcs with bloom, coral disruption ripples,
 *  product nodes igniting coral/amber and cooling to mint, a gold scan-pulse following
 *  the agent's focus, and tiny mono labels. Every visual is DERIVED from the semantic
 *  WS stream (mapModel/layers) — the backend never sends pixels. Reduced-motion + keyboard
 *  + responsive. Basemap is pure deck.gl GeoJSON for exact palette fidelity (worldGeo.ts);
 *  the @deck.gl/google-maps interleaved path is a documented one-component swap. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { MapView, _GlobeView as GlobeView } from "@deck.gl/core";
import { useEventStream } from "../../lib/useStream";
import { reduceMapState } from "../../lib/mapModel";
import type { Focus } from "../../lib/mapModel";
import { buildLayers, type MapViewKind } from "../../lib/map/layers";
import type { NetNode } from "../../lib/map/network";
import { API_BASE } from "../../lib/api";
import { ambientField, fetchRecentEvents, fixtureEvents, tickerItems, type IntelEvent, type TickerItem } from "../../lib/intel";
import Callouts from "./Callouts";
import RippleLabels from "./RippleLabels";
import NarrationLine from "./NarrationLine";
import Ticker, { TICKER_HEIGHT } from "./Ticker";

/** replay/demo mode keeps the intel feed deterministic; live mode polls the endpoint. */
function isReplayMode(): boolean {
  if (typeof window === "undefined") return true;
  const q = new URLSearchParams(window.location.search).get("demo");
  const mode = q ?? (import.meta.env.VITE_DEMO_MODE as string | undefined) ?? "replay";
  return mode !== "live";
}

interface PinnedFocus {
  lon: number;
  lat: number;
  label: string;
  url: string;
}

interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
  minZoom: number;
  maxZoom: number;
}

const FLAT_VIEW: ViewState = {
  longitude: 28,
  latitude: 26,
  zoom: 1.35,
  pitch: 0,
  bearing: 0,
  minZoom: 1.1, // keep one world filling the viewport — no horizontal wrap/duplication
  maxZoom: 8,
};

const GLOBE_VIEW: ViewState = {
  longitude: 24,
  latitude: 16,
  zoom: 2.45, // comfortably fills the panel without cropping poles (human-tuned)
  pitch: 0,
  bearing: 0,
  minZoom: 0.5,
  maxZoom: 6,
};

const VIEW_CFG = {
  flat: { initial: FLAT_VIEW, focusZoom: 2.3, rotate: false },
  globe: { initial: GLOBE_VIEW, focusZoom: 2.7, rotate: true },
} as const;

const ROTATE_DEG_PER_SEC = 3.2;

/** ?view=globe|flat — globe is the default; flat is the instant fallback. */
function resolveView(): MapViewKind {
  if (typeof window === "undefined") return "globe";
  const q = new URLSearchParams(window.location.search).get("view");
  if (q === "flat" || q === "globe") return q;
  const env = (import.meta.env.VITE_MAP_VIEW as string | undefined)?.toLowerCase();
  return env === "flat" ? "flat" : "globe";
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    if (typeof matchMedia === "undefined") return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduced;
}

/** Measure a container so we can hand deck.gl explicit pixel dimensions — more reliable
 *  than its default '100%' sizing, which can leave the backing buffer at 300×150. */
function useMeasure<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      setSize({ w: Math.round(r.width), h: Math.round(r.height) });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

/** Combined rAF engine: drives the animation clock AND the camera.
 *  - globe idle: slow auto-rotation; flat idle: still.
 *  - a new agent focus flies the camera there and dwells; user interaction pauses both.
 *  - reduced-motion: no loop; the camera jumps to focus, visuals are static. */
function useMapEngine(view: MapViewKind, reduced: boolean, focus: Focus | null, holdFocus = false) {
  const cfg = VIEW_CFG[view];
  const [viewState, setViewState] = useState<ViewState>(cfg.initial);
  const [time, setTime] = useState(0);

  // while a run is in progress the camera must HOLD the incident region — no idle drift.
  const holdRef = useRef(holdFocus);
  holdRef.current = holdFocus;

  const cur = useRef<ViewState>({ ...cfg.initial });
  const target = useRef({ longitude: cfg.initial.longitude, latitude: cfg.initial.latitude, zoom: cfg.initial.zoom });
  const dwellUntil = useRef(0);
  const interacting = useRef(false);
  const userZoomed = useRef(false); // once the user zooms, their zoom level wins and persists
  const lastEmit = useRef(0);
  const clock = useRef(0);

  // reset camera when the view kind changes
  useEffect(() => {
    cur.current = { ...cfg.initial };
    target.current = { longitude: cfg.initial.longitude, latitude: cfg.initial.latitude, zoom: cfg.initial.zoom };
    setViewState({ ...cfg.initial });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  // fly to a new agent focus (and dwell there before resuming idle rotation).
  // Zoom: hold the user's zoom if they've set one, else use focusZoom — never reset.
  useEffect(() => {
    if (!focus) return;
    const zoom = userZoomed.current ? cur.current.zoom : cfg.focusZoom;
    target.current = { longitude: focus.lon, latitude: focus.lat, zoom };
    dwellUntil.current = (typeof performance !== "undefined" ? performance.now() : 0) + 11_000;
    if (reduced) {
      cur.current = { ...cur.current, longitude: focus.lon, latitude: focus.lat, zoom };
      setViewState({ ...cur.current });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.lon, focus?.lat, reduced, view]);

  useEffect(() => {
    if (reduced) return;
    let raf = 0;
    let start: number | null = null;
    let last = 0;
    const loop = (ts: number) => {
      if (start === null) {
        start = ts;
        last = ts;
      }
      const dt = Math.min((ts - last) / 1000, 0.05);
      last = ts;
      const tnow = (ts - start) / 1000;

      const idle = ts > dwellUntil.current && !interacting.current && !holdRef.current;
      if (cfg.rotate && idle) {
        // idle = slow longitude spin ONLY; zoom and latitude are preserved (never
        // auto-return to a default), so user zoom and fly-to zoom both persist.
        target.current.longitude += ROTATE_DEG_PER_SEC * dt;
      }
      // frame-rate-independent easing toward the target
      const e = 1 - Math.pow(1 - 0.09, dt * 60);
      cur.current.longitude += (target.current.longitude - cur.current.longitude) * e;
      cur.current.latitude += (target.current.latitude - cur.current.latitude) * e;
      cur.current.zoom += (target.current.zoom - cur.current.zoom) * e;

      if (tnow - lastEmit.current >= 0.033) {
        lastEmit.current = tnow;
        clock.current = tnow;
        setTime(tnow);
        setViewState({ ...cfg.initial, ...cur.current });
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, reduced]);

  const onViewStateChange = useCallback((params: { viewState: ViewState; interactionState?: Record<string, boolean> }) => {
    const vs = params.viewState;
    cur.current = { ...cur.current, ...vs };
    target.current = { longitude: vs.longitude, latitude: vs.latitude, zoom: vs.zoom };
    const is = params.interactionState ?? {};
    interacting.current = !!(is.isDragging || is.isZooming || is.isPanning || is.isRotating);
    if (is.isZooming) userZoomed.current = true; // user zoom wins from here on
    if (interacting.current) dwellUntil.current = (typeof performance !== "undefined" ? performance.now() : 0) + 3_500;
    setViewState({ ...cfg.initial, ...vs });
  }, [cfg.initial]);

  // imperative camera command (ticker clicks, faultline:focus from C2 evidence chips)
  const flyTo = useCallback(
    (lon: number, lat: number) => {
      const zoom = userZoomed.current ? cur.current.zoom : cfg.focusZoom;
      target.current = { longitude: lon, latitude: lat, zoom };
      dwellUntil.current = (typeof performance !== "undefined" ? performance.now() : 0) + 12_000;
      if (reduced) {
        cur.current = { ...cur.current, longitude: lon, latitude: lat, zoom };
        setViewState({ ...cur.current });
      }
    },
    [cfg.focusZoom, reduced]
  );

  return { viewState, time, onViewStateChange, flyTo };
}

const PHASE_LABEL: Record<string, string> = {
  idle: "Standing by",
  scan: "Scanning world events",
  trace: "Tracing exposure paths",
  assess: "Quantifying exposure",
  approve: "Awaiting approval",
  resource: "Securing alternate supply",
  verify: "Verifying coverage",
  done: "Run complete",
};

export default function MapPanel() {
  const { messages, send } = useEventStream();
  const reduced = usePrefersReducedMotion();
  const [view] = useState<MapViewKind>(resolveView);

  const [boxRef, size] = useMeasure<HTMLElement>();

  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const state = useMemo(() => reduceMapState(messages), [messages]);
  const runActive = state.phase !== "idle" && state.phase !== "done";
  const { viewState, time, onViewStateChange, flyTo } = useMapEngine(view, reduced, state.focus, runActive);

  // live intelligence feed — deterministic fixture in replay, polled in live mode
  const [events, setEvents] = useState<IntelEvent[]>(() => fixtureEvents());
  useEffect(() => {
    if (isReplayMode()) return;
    let alive = true;
    const poll = () => fetchRecentEvents(API_BASE).then((ev) => alive && setEvents(ev));
    poll();
    const t = setInterval(poll, 30_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  const ambient = useMemo(() => ambientField(events), [events]);
  const ticker = useMemo(() => tickerItems(events), [events]);

  const layers = useMemo(
    () => buildLayers(state, time, reduced, view, hoveredId, ambient, { lon: viewState.longitude, lat: viewState.latitude }),
    [state, time, reduced, view, hoveredId, ambient, viewState.longitude, viewState.latitude]
  );
  const deckView = useMemo(() => (view === "globe" ? new GlobeView({ resolution: 12 }) : new MapView({ repeat: false })), [view]);

  // click-to-fly: ticker items and C2 evidence chips both dispatch `faultline:focus`
  const [pinned, setPinned] = useState<PinnedFocus | null>(null);
  useEffect(() => {
    const onFocus = (e: Event) => {
      const d = (e as CustomEvent).detail ?? {};
      if (typeof d.lon === "number" && typeof d.lat === "number") {
        flyTo(d.lon, d.lat);
        setPinned({ lon: d.lon, lat: d.lat, label: d.label ?? "", url: d.url ?? "" });
      }
    };
    window.addEventListener("faultline:focus", onFocus as EventListener);
    return () => window.removeEventListener("faultline:focus", onFocus as EventListener);
  }, [flyTo]);
  useEffect(() => {
    if (!pinned) return;
    const t = setTimeout(() => setPinned(null), 10_000);
    return () => clearTimeout(t);
  }, [pinned]);

  const pickTicker = (it: TickerItem) =>
    window.dispatchEvent(new CustomEvent("faultline:focus", { detail: { lon: it.lon, lat: it.lat, label: it.label, url: it.url } }));

  const getTooltip = ({ object, layer }: { object?: NetNode; layer?: { id: string } }) => {
    if (!object || layer?.id !== "nodes") return null;
    const n = object;
    let detail: string;
    if (n.kind === "product") {
      const ex = state.exposureByProduct[n.id];
      const st = state.secured.has(n.id) ? "secured" : ex?.status?.replace("_", " ") ?? "nominal";
      detail = `Finished product · ${st}${ex ? ` · ${ex.daysOfCover}d cover` : ""}`;
    } else {
      const flag = state.recommended === n.id ? " · recommended alternate" : "";
      detail = `${n.short}${n.country ? ` · ${n.country}` : ""}${flag}`;
    }
    return {
      html: `<div style="font-weight:600;margin-bottom:2px">${n.name}</div><div style="opacity:.8">${detail}</div>`,
      style: {
        background: "rgba(6,13,23,0.95)",
        color: "#E6EDF6",
        border: "1px solid rgba(138,155,179,0.3)",
        borderRadius: "6px",
        fontSize: "11px",
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        padding: "7px 9px",
        maxWidth: "240px",
      },
    };
  };

  const approve = () => {
    if (!state.approvalPending) return;
    send({
      type: "approval.decision",
      ts: new Date().toISOString(),
      run_id: state.activeRunId,
      payload: { approval_id: state.approvalPending.approval_id, approved: true },
    });
  };

  return (
    <section
      ref={boxRef}
      className={"panel" + (state.simulated ? " sim-frame" : "")}
      style={{
        position: "relative",
        height: "100%",
        overflow: "hidden",
        background:
          view === "globe"
            ? // deep space + a soft atmospheric halo behind the planet
              "radial-gradient(ellipse 56% 56% at 50% 47%, rgba(64,170,200,0.12) 0%, rgba(24,70,110,0.06) 40%, transparent 64%), radial-gradient(ellipse 130% 120% at 50% 45%, #070e19 0%, #03070d 75%)"
            : "radial-gradient(ellipse 80% 70% at 42% 38%, #0c1a2c 0%, var(--base) 62%)",
      }}
      aria-label="Living supply-chain map"
    >
      {view === "globe" && <Stars w={size.w} h={size.h} />}
      {size.w > 0 && (
        <DeckGL
          views={deckView}
          viewState={viewState}
          onViewStateChange={onViewStateChange as never}
          controller={{ dragRotate: false, keyboard: true, scrollZoom: { speed: 0.06, smooth: true } }}
          layers={layers}
          width={size.w}
          height={size.h}
          style={{ position: "absolute", inset: "0" }}
          getCursor={({ isDragging }) => (isDragging ? "grabbing" : hoveredId ? "pointer" : "crosshair")}
          onHover={(info) => setHoveredId(info.layer?.id === "nodes" ? ((info.object as NetNode | undefined)?.id ?? null) : null)}
          getTooltip={getTooltip as never}
        />
      )}

      {size.w > 0 && (
        <>
          <RippleLabels state={state} view={deckView} viewState={viewState as unknown as Record<string, number>} size={size} kind={view} />
          <Callouts state={state} view={deckView} viewState={viewState as unknown as Record<string, number>} size={size} kind={view} />
        </>
      )}

      {/* live intelligence ticker (bottom strip) */}
      <Ticker items={ticker} onPick={pickTicker} />

      {/* click-to-fly callout (ticker item / C2 evidence chip) */}
      {pinned && (
        <div
          className="fade-up"
          style={{ position: "absolute", top: 56, left: "50%", transform: "translateX(-50%)", maxWidth: "62%", zIndex: 7 }}
        >
          <div
            className="panel"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "9px 13px",
              borderColor: "rgba(45,212,191,0.45)",
              boxShadow: "0 6px 22px rgba(0,0,0,0.5)",
              background: "rgba(6,13,23,0.95)",
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--graph-edge)", boxShadow: "var(--glow-teal)", flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.3 }}>{pinned.label || "Located on map"}</span>
            {pinned.url && (
              <a
                href={pinned.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mono"
                style={{ fontSize: 10.5, color: "var(--graph-edge)", whiteSpace: "nowrap", textDecoration: "none", flexShrink: 0 }}
              >
                source ↗
              </a>
            )}
            <button
              onClick={() => setPinned(null)}
              aria-label="Dismiss"
              className="mono"
              style={{ background: "none", border: "none", color: "var(--ink-dim)", cursor: "pointer", fontSize: 13, lineHeight: 1, flexShrink: 0 }}
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* top-left — identity + run */}
      <div style={{ position: "absolute", top: 14, left: 16, pointerEvents: "none" }}>
        <div className="eyebrow">Living Map</div>
        <div className="mono dim" style={{ fontSize: 11, marginTop: 3 }}>
          {state.activeRunId ?? "—"}
        </div>
        <div className="mono dim" style={{ fontSize: 10, marginTop: 2, opacity: 0.8 }}>
          Northwind Provisions · F&amp;B
        </div>
      </div>

      {/* top-right — mode + phase stepper */}
      <div style={{ position: "absolute", top: 12, right: 14, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
        <span className={"chip " + (state.simulated ? "sim" : "ok")}>
          <span className="dot" />
          {state.simulated ? "SIMULATED" : "LIVE"}
        </span>
        <PhaseStepper steps={state.steps} activeStep={state.activeStep} />
        <div className="mono dim" style={{ fontSize: 10.5 }}>{PHASE_LABEL[state.phase] ?? state.phase}</div>
      </div>

      {/* bottom-left — live narration line, above the legend */}
      <NarrationLine state={state} bottom={TICKER_HEIGHT + 12 + 98} />

      {/* bottom-left — legend */}
      <Legend />

      {/* approval gate — appears only while the run is paused on the operator */}
      {state.approvalPending && (
        <div className="fade-up" style={{ position: "absolute", top: 16, left: "50%", transform: "translateX(-50%)", maxWidth: "56%" }}>
          <button
            onClick={approve}
            className="panel"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "10px 16px",
              cursor: "pointer",
              color: "var(--ink)",
              borderColor: "rgba(245,181,68,0.5)",
              boxShadow: "var(--glow-amber)",
              textAlign: "left",
              font: "inherit",
            }}
          >
            <span className="chip warn" style={{ border: "none", padding: 0 }}>
              <span className="dot" />
            </span>
            <span style={{ fontSize: 12.5 }}>
              <strong style={{ letterSpacing: "0.02em" }}>Approval required</strong>
              <span className="dim" style={{ display: "block", fontSize: 11, marginTop: 2 }}>
                {state.approvalPending.summary.slice(0, 96)}…
              </span>
            </span>
            <span className="mono" style={{ fontSize: 11, color: "var(--signal)", marginLeft: "auto", whiteSpace: "nowrap" }}>
              Approve ▸
            </span>
          </button>
        </div>
      )}
    </section>
  );
}

function PhaseStepper({ steps, activeStep }: { steps: { id: string; status: string }[]; activeStep: string | null }) {
  const order = ["scan", "trace", "assess", "approve", "resource", "verify"];
  const byId = Object.fromEntries(steps.map((s) => [s.id, s.status]));
  return (
    <div style={{ display: "flex", gap: 5 }} aria-hidden>
      {order.map((id) => {
        const st = byId[id] ?? "pending";
        const active = activeStep === id;
        const color =
          st === "done" ? "var(--secured)" : active ? "var(--signal)" : st === "active" ? "var(--signal)" : "var(--ink-faint)";
        return (
          <span
            key={id}
            style={{
              width: active ? 16 : 8,
              height: 4,
              borderRadius: 4,
              background: color,
              opacity: st === "pending" ? 0.4 : 1,
              boxShadow: active ? "0 0 8px rgba(245,181,68,0.7)" : "none",
              transition: "width 0.3s ease, background 0.3s ease",
            }}
          />
        );
      })}
    </div>
  );
}

/** Deterministic starfield behind the globe (deep-space feel; pure CSS box-shadows). */
function Stars({ w, h }: { w: number; h: number }) {
  const shadow = useMemo(() => {
    if (!w || !h) return "";
    let s = 1234567;
    const rnd = () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
    const parts: string[] = [];
    for (let i = 0; i < 130; i++) {
      const x = Math.round(rnd() * w);
      const y = Math.round(rnd() * h);
      const a = (0.1 + rnd() * 0.45).toFixed(2);
      const teal = rnd() < 0.12;
      const blur = rnd() < 0.25 ? 2 : 1;
      parts.push(`${x}px ${y}px ${blur}px ${teal ? `rgba(45,212,191,${a})` : `rgba(214,228,247,${a})`}`);
    }
    return parts.join(",");
  }, [w, h]);
  if (!shadow) return null;
  return (
    <div aria-hidden style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}>
      <div style={{ position: "absolute", width: 1, height: 1, borderRadius: "50%", boxShadow: shadow }} />
    </div>
  );
}

function Legend() {
  const items: [string, string][] = [
    ["var(--graph-edge)", "Supply route"],
    ["var(--risk)", "Disruption"],
    ["var(--signal)", "Agent focus"],
    ["var(--secured)", "Secured"],
    ["rgba(138,155,179,0.75)", "Monitored event"],
  ];
  return (
    <div style={{ position: "absolute", bottom: TICKER_HEIGHT + 12, left: 16, display: "flex", flexDirection: "column", gap: 5, pointerEvents: "none" }}>
      {items.map(([c, label]) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ width: 8, height: 8, borderRadius: 50, background: c, boxShadow: `0 0 7px ${c}` }} />
          <span className="mono dim" style={{ fontSize: 10 }}>{label}</span>
        </div>
      ))}
    </div>
  );
}

/** The living map — THE hero (Session C1 owns).
 *  deck.gl world map: teal supplier-graph arcs with bloom, coral disruption ripples,
 *  product nodes igniting coral/amber and cooling to mint, a gold scan-pulse following
 *  the agent's focus, and tiny mono labels. Every visual is DERIVED from the semantic
 *  WS stream (mapModel/layers) — the backend never sends pixels. Reduced-motion + keyboard
 *  + responsive. Basemap is pure deck.gl GeoJSON for exact palette fidelity (worldGeo.ts);
 *  the @deck.gl/google-maps interleaved path is a documented one-component swap. */
import { useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { MapView } from "@deck.gl/core";
import { useEventStream } from "../../lib/useStream";
import { reduceMapState } from "../../lib/mapModel";
import { buildLayers } from "../../lib/map/layers";

const INITIAL_VIEW = {
  longitude: 28,
  latitude: 26,
  zoom: 1.35,
  pitch: 0,
  bearing: 0,
  minZoom: 0.8,
  maxZoom: 8,
};

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

/** rAF clock (seconds). Frozen when reduced-motion is requested. */
function useClock(active: boolean): number {
  const [t, setT] = useState(0);
  const ref = useRef(0);
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let start: number | null = null;
    const loop = (ts: number) => {
      if (start === null) start = ts;
      const next = (ts - start) / 1000;
      // throttle React updates to ~30fps; deck.gl interpolates smoothly enough
      if (next - ref.current >= 0.033) {
        ref.current = next;
        setT(next);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active]);
  return t;
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
  const time = useClock(!reduced);

  const [boxRef, size] = useMeasure<HTMLElement>();

  const state = useMemo(() => reduceMapState(messages), [messages]);
  const layers = useMemo(() => buildLayers(state, time, reduced), [state, time, reduced]);

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
        background: "radial-gradient(ellipse 80% 70% at 42% 38%, #0c1a2c 0%, var(--base) 62%)",
      }}
      aria-label="Living supply-chain map"
    >
      {size.w > 0 && (
        <DeckGL
          views={new MapView({ repeat: true })}
          initialViewState={INITIAL_VIEW}
          controller={{ dragRotate: false, keyboard: true, scrollZoom: { speed: 0.06, smooth: true } }}
          layers={layers}
          width={size.w}
          height={size.h}
          style={{ position: "absolute", inset: "0" }}
          getCursor={() => "crosshair"}
        />
      )}

      {/* top-left — identity + run */}
      <div style={{ position: "absolute", top: 14, left: 16, pointerEvents: "none" }}>
        <div className="eyebrow">Living Map</div>
        <div className="mono dim" style={{ fontSize: 11, marginTop: 3 }}>
          {state.activeRunId ?? "—"}
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

      {/* bottom-left — legend */}
      <Legend />

      {/* bottom — status note */}
      {state.statusNote && (
        <div
          className="mono"
          style={{
            position: "absolute",
            bottom: 14,
            left: "50%",
            transform: "translateX(-50%)",
            maxWidth: "62%",
            textAlign: "center",
            fontSize: 11.5,
            color: "var(--ink-dim)",
            pointerEvents: "none",
          }}
        >
          {state.statusNote}
        </div>
      )}

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

function Legend() {
  const items: [string, string][] = [
    ["var(--graph-edge)", "Supply route"],
    ["var(--risk)", "Disruption"],
    ["var(--signal)", "Agent focus"],
    ["var(--secured)", "Secured"],
  ];
  return (
    <div style={{ position: "absolute", bottom: 14, left: 16, display: "flex", flexDirection: "column", gap: 5, pointerEvents: "none" }}>
      {items.map(([c, label]) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ width: 8, height: 8, borderRadius: 50, background: c, boxShadow: `0 0 7px ${c}` }} />
          <span className="mono dim" style={{ fontSize: 10 }}>{label}</span>
        </div>
      ))}
    </div>
  );
}

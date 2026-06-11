/** Accordion rail + follow-the-agent mode (C2 panels).
 *
 *  The shell (App.tsx, C1-owned) stacks the four panels in a column; we can't edit it,
 *  so the accordion is implemented inside the panels themselves: each renders either a
 *  one-line summary strip (collapsed) or its full body (expanded). Exactly one of the
 *  three run-phase panels is expanded at a time.
 *
 *  Follow mode (default ON) auto-expands the panel matching the live run phase:
 *    scan/trace → Mission Control · ranked_exposures → Action Board ·
 *    approval gate → Mission Control (gate) · brief → Decision Log.
 *  A manual click on any strip pins that panel and turns follow OFF; the follow control
 *  in the expanded header resumes it. What-If is collapsible but never a follow target. */

import { useSyncExternalStore, type ReactNode } from "react";
import { useFaultline, type FaultlineState } from "./store";

export type PanelId = "mission" | "action" | "decision" | "whatif";

interface UiState {
  mode: "follow" | "manual";
  manualPanel: PanelId;
}

let ui: UiState = { mode: "follow", manualPanel: "mission" };
const uiListeners = new Set<() => void>();
function emitUi() {
  for (const l of uiListeners) l();
}

export function pinPanel(id: PanelId) {
  ui = { mode: "manual", manualPanel: id };
  emitUi();
}
export function enableFollow() {
  ui = { ...ui, mode: "follow" };
  emitUi();
}

function useUi(): UiState {
  return useSyncExternalStore(
    (cb) => {
      uiListeners.add(cb);
      return () => uiListeners.delete(cb);
    },
    () => ui,
    () => ui,
  );
}

/** Which panel the agent's run phase wants in focus. Keyed off the authoritative
 *  plan.active_step (server-driven, independent of whether the approval round-trips):
 *  scan/trace → Mission Control · assess (once exposures land) / resource / verify →
 *  Action Board · approve → Mission Control (gate prominent) · brief → Decision Log. */
export function followTarget(s: FaultlineState): PanelId {
  if (s.brief) return "decision";
  const step = s.plan?.active_step ?? null;
  if (step === "approve") return "mission";
  if (step === "resource" || step === "verify") return "action";
  if (step === "assess" && s.exposures.length) return "action";
  if (step === "scan" || step === "trace" || step === "assess") return "mission";
  // run complete (active_step null) — settle on the board if anything was assessed
  return s.exposures.length ? "action" : "mission";
}

export function usePanelOpen(id: PanelId): boolean {
  const data = useFaultline();
  const u = useUi();
  const open = u.mode === "follow" ? followTarget(data) === id : u.manualPanel === id;
  return open;
}

export function useFollowMode(): "follow" | "manual" {
  return useUi().mode;
}

/** The accordion shell for one panel: strip when collapsed, full panel when open. */
export function AccordionPanel({
  id,
  title,
  strip,
  meta,
  children,
}: {
  id: PanelId;
  title: string;
  strip: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
}) {
  const open = usePanelOpen(id);
  const mode = useFollowMode();

  if (!open) {
    const isFollowing = mode === "follow";
    return (
      <button
        type="button"
        className="fl-strip"
        onClick={() => pinPanel(id)}
        aria-expanded={false}
        aria-label={`Expand ${title}`}
      >
        <span className="fl-strip__title">{title}</span>
        {isFollowing && <span className="fl-strip__dot" aria-hidden />}
        <span className="fl-strip__summary">{strip}</span>
        <span className="fl-strip__chev" aria-hidden>▸</span>
      </button>
    );
  }

  return (
    <section className="fl-panel fl-panel--open">
      <div className="fl-panel__head">
        <span className="fl-panel__title">{title}</span>
        <span style={{ marginLeft: "auto" }} />
        {meta != null && <span className="fl-panel__meta">{meta}</span>}
        <FollowControl currentId={id} />
      </div>
      <div className="fl-panel__body">{children}</div>
    </section>
  );
}

function FollowControl({ currentId }: { currentId: PanelId }) {
  const mode = useFollowMode();
  const following = mode === "follow";
  return (
    <button
      type="button"
      className={`fl-follow ${following ? "fl-follow--on" : ""}`}
      onClick={() => (following ? pinPanel(currentId) : enableFollow())}
      title={following ? "Following the agent — click to pin this panel" : "Resume following the agent"}
      aria-pressed={following}
    >
      <span className={`fl-dot ${following ? "fl-dot--live" : "fl-dot--idle"}`} />
      {following ? "Following" : "Follow"}
    </button>
  );
}

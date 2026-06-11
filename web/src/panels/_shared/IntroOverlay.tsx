/** First-open intro overlay (C2). Three bullets + a "Watch a live incident" CTA.
 *  Dismissal is remembered in localStorage; it NEVER shows during ?demo=replay so the
 *  recording path is untouched. Rendered through a portal to document.body because the
 *  shell (App.tsx) is C1's — mounted from Mission Control. */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

const SEEN_KEY = "faultline_intro_seen";

function isReplayRecording(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("demo") === "replay";
  } catch {
    return false;
  }
}
function alreadySeen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

export default function IntroOverlay() {
  const [open, setOpen] = useState<boolean>(() => !isReplayRecording() && !alreadySeen());

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  function dismiss() {
    try {
      window.localStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* private mode — fine, it just shows again next time */
    }
    setOpen(false);
  }

  return createPortal(
    <div
      className="fl-intro"
      role="dialog"
      aria-modal="true"
      aria-label="Welcome to Faultline"
      onClick={(e) => {
        if (e.target === e.currentTarget) dismiss();
      }}
    >
      <div className="fl-intro__card">
        <div className="fl-intro__brand">FAULTLINE</div>
        <div className="fl-intro__tag">Supply Chain Control Tower</div>
        <ul className="fl-intro__bullets">
          <li>Watches live world events</li>
          <li>Traces them through your supplier graph</li>
          <li>Re-sources before you run out</li>
        </ul>
        <button type="button" className="fl-btn fl-btn--primary fl-intro__cta" onClick={dismiss} autoFocus>
          ▶ Watch a live incident
        </button>
        <button type="button" className="fl-intro__skip" onClick={dismiss}>
          Skip
        </button>
      </div>
    </div>,
    document.body,
  );
}

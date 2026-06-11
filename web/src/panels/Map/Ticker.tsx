/** Intel ticker (Session C1 owns) — a thin, quiet scrolling strip of real recent-event
 *  headlines at the bottom of the map. Clicking an item flies the camera there and opens
 *  a callout (routed through the shared `faultline:focus` CustomEvent, the same channel
 *  C2 evidence chips use). Scroll pauses on hover; reduced-motion renders it static. */
import type { TickerItem } from "../../lib/intel";

export const TICKER_HEIGHT = 28;

export default function Ticker({ items, onPick }: { items: TickerItem[]; onPick: (it: TickerItem) => void }) {
  if (!items.length) return null;
  // duplicate the run so the marquee loops seamlessly
  const run = [...items, ...items];

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height: TICKER_HEIGHT,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0 12px",
        background: "linear-gradient(0deg, rgba(6,13,23,0.96), rgba(6,13,23,0.82))",
        borderTop: "1px solid var(--hairline)",
        overflow: "hidden",
        zIndex: 4,
      }}
      aria-label="Live intelligence ticker"
    >
      <span className="eyebrow" style={{ flexShrink: 0, color: "var(--ink-faint)", letterSpacing: "0.2em" }}>
        Intel
      </span>
      <span style={{ width: 1, height: 14, background: "var(--hairline)", flexShrink: 0 }} />
      <div style={{ position: "relative", flex: 1, overflow: "hidden", height: "100%" }}>
        <div className="ticker-track" style={{ display: "inline-flex", alignItems: "center", height: "100%", whiteSpace: "nowrap" }}>
          {run.map((it, i) => (
            <button
              key={`${it.id}-${i}`}
              className="ticker-item mono"
              onClick={() => onPick(it)}
              title={it.label}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                padding: "0 18px",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                color: "var(--ink-dim)",
                height: "100%",
              }}
            >
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: "50%",
                  background: it.simulated ? "var(--signal)" : "var(--graph-edge)",
                  boxShadow: `0 0 6px ${it.simulated ? "var(--signal)" : "var(--graph-edge)"}`,
                  flexShrink: 0,
                }}
              />
              {it.text}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

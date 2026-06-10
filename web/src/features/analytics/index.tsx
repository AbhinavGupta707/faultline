/** Analytics panel — Session G owns this folder's internals; props are FROZEN
 *  (contracts/components.md §2). Renders the 60-day risk history served by
 *  GET {apiBase}/analytics/summary, falling back to the bundled golden fixture until
 *  the endpoint is live. Quiet and data-dense per faultline_ui_design_prompts.md —
 *  all the boldness is spent on the map, not here. */
import { useEffect, useMemo, useRef, useState } from "react";

import "./analytics.css";
import { FIXTURE_SUMMARY } from "./fixture";
import type { AnalyticsSummary, RiskPoint } from "./types";

export interface AnalyticsPanelProps {
  apiBase: string;
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function sevColor(sev: number): string {
  if (sev >= 0.55) return "var(--risk)";
  if (sev >= 0.3) return "var(--watch)";
  return "var(--graph-edge)";
}

function fmtUsd(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `$${Math.round(v / 1000)}k`;
  return `$${Math.round(v)}`;
}

/** Animated count-up that respects prefers-reduced-motion. */
function useCountUp(target: number, ms = 900): number {
  const [val, setVal] = useState(prefersReducedMotion() ? target : 0);
  const raf = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setVal(target);
      return;
    }
    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(from + (target - from) * eased);
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [target, ms]);
  return val;
}

interface Series {
  product_id: string;
  product_name: string;
  points: RiskPoint[];
  latest: RiskPoint;
}

function groupSeries(rows: RiskPoint[]): Series[] {
  const by = new Map<string, RiskPoint[]>();
  for (const r of rows) {
    const arr = by.get(r.product_id) ?? [];
    arr.push(r);
    by.set(r.product_id, arr);
  }
  const out: Series[] = [];
  for (const [pid, pts] of by) {
    pts.sort((a, b) => a.date.localeCompare(b.date));
    out.push({
      product_id: pid,
      product_name: pts[0].product_name ?? pid,
      points: pts,
      latest: pts[pts.length - 1],
    });
  }
  // most-at-risk first
  out.sort((a, b) => b.latest.severity_avg - a.latest.severity_avg);
  return out;
}

function Sparkline({ points }: { points: RiskPoint[] }) {
  const W = 96;
  const H = 26;
  const PAD = 2;
  const sevs = points.map((p) => p.severity_avg);
  const max = Math.max(0.001, ...sevs);
  const n = points.length;
  const x = (i: number) => (n <= 1 ? W / 2 : PAD + (i * (W - 2 * PAD)) / (n - 1));
  const y = (v: number) => H - PAD - (v / max) * (H - 2 * PAD);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.severity_avg).toFixed(1)}`).join(" ");
  const area = `${line} L${x(n - 1).toFixed(1)},${H - PAD} L${x(0).toFixed(1)},${H - PAD} Z`;
  const color = sevColor(points[points.length - 1].severity_avg);
  return (
    <svg className="fa-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      <path className="fa-area" d={area} style={{ fill: color }} />
      <path d={line} style={{ stroke: color }} />
    </svg>
  );
}

export default function AnalyticsPanel({ apiBase }: AnalyticsPanelProps) {
  const [data, setData] = useState<AnalyticsSummary>(FIXTURE_SUMMARY);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!apiBase) return;
    (async () => {
      try {
        const res = await fetch(`${apiBase}/analytics/summary`, { headers: { accept: "application/json" } });
        if (!res.ok) throw new Error(String(res.status));
        const json = (await res.json()) as AnalyticsSummary;
        if (!cancelled && json && Array.isArray(json.risk_over_time)) {
          setData(json);
          setLive(true);
        }
      } catch {
        /* keep the bundled fixture — never a dead panel */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const series = useMemo(() => groupSeries(data.risk_over_time ?? []), [data]);
  const maxIncidents = useMemo(
    () => Math.max(1, ...data.top_chokepoints.map((c) => c.incident_count)),
    [data],
  );
  const avoided = useCountUp(data.dollars_at_risk_avoided_usd);

  return (
    <section className="panel fl-analytics" aria-label="Analytics — risk history">
      <div className="fa-head">
        <div className="eyebrow">Analytics · {data.window_days}-day risk history</div>
        <span className="fa-src">
          <span className={`fa-dot ${live ? "" : "fixture"}`} />
          {live ? "live" : "fixture"}
          {data.includes_backfill && <span className="fa-tag">incl. backfill</span>}
        </span>
      </div>

      <div className="fa-counter">
        <div className="fa-val">{fmtUsd(avoided)}</div>
        <div className="fa-sub">
          $ at risk averted · {data.runs_count} runs analyzed
        </div>
      </div>

      <div>
        <div className="fa-section-label">Risk over time · per product line</div>
        {series.length === 0 && <div className="fa-empty">No runs in window yet.</div>}
        {series.map((s) => (
          <div className="fa-spark-row" key={s.product_id}>
            <div className="fa-prod" title={s.product_name}>
              <span className="fa-sevdot" style={{ background: sevColor(s.latest.severity_avg) }} />
              {s.product_name}
            </div>
            <Sparkline points={s.points} />
            <div className="fa-metric" title="latest $ at risk">
              {fmtUsd(s.latest.dollars_at_risk_usd)}
            </div>
          </div>
        ))}
      </div>

      <div>
        <div className="fa-section-label">Recurring chokepoints</div>
        {data.top_chokepoints.length === 0 && <div className="fa-empty">None flagged.</div>}
        {data.top_chokepoints.map((c) => (
          <div className="fa-choke" key={c.supplier_id}>
            <div className="fa-choke-name">
              {c.name}
              <span className="fa-tier">{c.country}{c.tier ? ` · T${c.tier}` : ""}</span>
            </div>
            <div className="fa-bar-wrap">
              <span
                className="fa-bar"
                style={{ width: `${(c.incident_count / maxIncidents) * 64 + 4}px` }}
              />
              <span className="fa-count">{c.incident_count}×</span>
            </div>
            <div className="fa-prods">
              {c.products_affected.map((p) => (
                <span className="fa-chip" key={p}>{p.replace("prd-", "")}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

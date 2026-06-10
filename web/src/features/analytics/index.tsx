/** Analytics panel — Session G owns this folder's internals; props are FROZEN
 *  (contracts/components.md §2). Phase 0 stub: renders the mount, notes the fixture fallback. */

export interface AnalyticsPanelProps {
  apiBase: string;
}

export default function AnalyticsPanel(_props: AnalyticsPanelProps) {
  return (
    <section className="panel" style={{ padding: 12 }}>
      <div className="eyebrow">Analytics · 60-day risk history</div>
      <p className="dim mono" style={{ fontSize: 12 }}>
        awaiting G — falls back to contracts/fixtures/analytics_summary.json until /analytics/summary is live
      </p>
    </section>
  );
}

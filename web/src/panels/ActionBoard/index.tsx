/** Action Board — ranked exposures + re-sourcing + the live negotiation call (UI prompt 4).
 *  Each row: product · days of cover · $ at risk (mono) · status pill. Expand to reveal
 *  the recommended alternate, the contingent PO card with Approve, and the verify result.
 *  A live-call panel renders call_event messages (Negotiator / Session E backend) to contract.
 *  Session C2 owns this folder. */
import { useEffect, useRef, useState } from "react";
import { StatusPill, Empty } from "../_shared/ui";
import { AccordionPanel } from "../_shared/accordion";
import {
  useFaultline,
  decideApproval,
  type Exposure,
  type AlternatesPayload,
  type DraftPO,
  type CallEvent,
  type VerifyResult,
} from "../_shared/store";
import { usd, usdCompact, days, pct, humanize } from "../_shared/format";
import { CountUp } from "../_shared/anim";
import { focusOnMap, type FocusDetail } from "../_shared/focus";

export default function ActionBoard() {
  const s = useFaultline();
  const exposures = [...s.exposures].sort((a, b) => a.rank - b.rank);
  const hasCall = s.callEvents.length > 0;
  const atRiskTotal = exposures
    .filter((e) => e.status === "at_risk")
    .reduce((sum, e) => sum + e.dollars_at_risk_usd, 0);
  const securedCount = exposures.filter((e) => e.status === "secured").length;

  const strip = exposures.length ? (
    <>
      <b>{exposures.length}</b> exposures
      {atRiskTotal > 0 ? <> · <span className="risk">{usdCompact(atRiskTotal)} at risk</span></> : null}
      {securedCount ? ` · ${securedCount} secured` : ""}
    </>
  ) : (
    <>awaiting exposures</>
  );

  return (
    <AccordionPanel
      id="action"
      title="Action Board"
      meta={exposures.length ? `${exposures.length} exposures` : undefined}
      strip={strip}
    >
      {exposures.length ? (
        <div className="fl-exps">
          {exposures.map((e) => (
            <ExposureRow
              key={e.exposure_id}
              exp={e}
              alternates={s.alternatesByExposure[e.exposure_id]}
              po={s.posByExposure[e.exposure_id]}
              verify={s.verifyByExposure[e.exposure_id]}
              pendingApprovalId={pendingApprovalFor(s, e.exposure_id)}
              focus={focusForExposure(s, e)}
            />
          ))}
        </div>
      ) : (
        <Empty>no exposures yet — the board fills as the agent quantifies risk</Empty>
      )}

      {hasCall && (
        <div style={{ marginTop: 14 }}>
          <div className="fl-eyebrow" style={{ marginBottom: 6 }}>Live call</div>
          <LiveCall events={s.callEvents} />
        </div>
      )}
    </AccordionPanel>
  );
}

function ExposureRow({
  exp,
  alternates,
  po,
  verify,
  pendingApprovalId,
  focus,
}: {
  exp: Exposure;
  alternates?: AlternatesPayload;
  po?: DraftPO;
  verify?: VerifyResult;
  pendingApprovalId?: string;
  focus?: FocusDetail | null;
}) {
  const [open, setOpen] = useState(false);
  const expandable = Boolean(alternates || po || verify || exp.rationale);

  return (
    <div className={`fl-exp fl-exp--${exp.status}`}>
      <button
        type="button"
        className="fl-exp__row"
        onClick={() => {
          if (focus) focusOnMap(focus); // fly the map to the disruption
          if (expandable) setOpen((o) => !o);
        }}
        aria-expanded={open}
        title={focus ? "Open details · focus the map on this disruption" : undefined}
      >
        <span className="fl-exp__rank">#{exp.rank}</span>
        <span>
          <span className="fl-exp__name">
            {exp.product_name}
            {focus && <span className="fl-exp__locate" aria-hidden>⌖</span>}
          </span>
          <span className="fl-exp__sub" style={{ display: "block" }}>{humanize(exp.component_id.replace(/^cmp-/, ""))}</span>
        </span>
        <span className="fl-exp__metric">
          <span className="v">{days(exp.days_of_cover)}</span>
          <span className="k">cover</span>
        </span>
        <span className="fl-exp__metric">
          <span className={`v ${exp.status === "at_risk" ? "v--risk" : ""}`}>
            <CountUp value={exp.dollars_at_risk_usd} format={usd} />
          </span>
          <span className="k">at risk</span>
        </span>
        <StatusPill status={exp.status} />
        {expandable ? (
          <span className={`fl-exp__caret ${open ? "fl-exp__caret--open" : ""}`} aria-hidden>
            ›
          </span>
        ) : (
          <span />
        )}
      </button>

      {open && (
        <div className="fl-exp__detail">
          <div className="fl-exp__rationale">{exp.rationale}</div>

          {alternates && <AlternateCard alternates={alternates} />}
          {po && <POCard po={po} pendingApprovalId={pendingApprovalId} />}
          {verify && <VerifyCard verify={verify} />}
        </div>
      )}
    </div>
  );
}

function AlternateCard({ alternates }: { alternates: AlternatesPayload }) {
  const rec =
    alternates.alternates.find((a) => a.supplier_id === alternates.recommended_supplier_id) ??
    alternates.alternates[0];
  if (!rec) return null;
  return (
    <div className="fl-card">
      <div className="fl-card__head">
        <span className="fl-rec">Recommended</span>
        <span className="fl-card__title">{rec.name}</span>
        <span className="fl-panel__meta" style={{ marginLeft: "auto" }}>match {pct(rec.match_score)}</span>
      </div>
      <dl className="fl-kv">
        <dt>Location</dt>
        <dd>{rec.country}</dd>
        <dt>Lead time</dt>
        <dd>{days(rec.expedited_lead_time_days ?? rec.lead_time_days)}{rec.expedited_lead_time_days ? " air" : ""}</dd>
        <dt>Capacity</dt>
        <dd>{humanize(rec.capacity)}</dd>
        {rec.certifications?.length ? (
          <>
            <dt>Certs</dt>
            <dd>{rec.certifications.join(" · ")}</dd>
          </>
        ) : null}
        {rec.est_unit_cost_usd != null ? (
          <>
            <dt>Unit cost</dt>
            <dd>${rec.est_unit_cost_usd.toFixed(2)}</dd>
          </>
        ) : null}
      </dl>
      {rec.rationale && <div className="fl-exp__rationale" style={{ marginTop: 7 }}>{rec.rationale}</div>}
      {alternates.alternates.length > 1 && (
        <div className="fl-panel__meta" style={{ marginTop: 7 }}>
          +{alternates.alternates.length - 1} other qualified{" "}
          {alternates.alternates.length - 1 === 1 ? "alternate" : "alternates"} considered
        </div>
      )}
    </div>
  );
}

function POCard({ po, pendingApprovalId }: { po: DraftPO; pendingApprovalId?: string }) {
  return (
    <div className="fl-card">
      <div className="fl-card__head">
        <span className="fl-eyebrow" style={{ color: "var(--graph-edge)" }}>Contingent purchase order</span>
        <span className="fl-panel__meta" style={{ marginLeft: "auto" }}>{po.po_id}</span>
      </div>
      <dl className="fl-kv">
        <dt>Supplier</dt>
        <dd>{po.supplier_name}</dd>
        <dt>Quantity</dt>
        <dd>{po.quantity.toLocaleString("en-US")} {po.unit}</dd>
        <dt>Unit price</dt>
        <dd>${po.unit_price_usd.toFixed(2)}</dd>
        <dt>Total</dt>
        <dd>{usd(po.total_usd)}</dd>
        <dt>Lead time</dt>
        <dd>{days(po.lead_time_days)}</dd>
        <dt>Need by</dt>
        <dd>{po.need_by_date}</dd>
        {po.ship_mode ? (
          <>
            <dt>Ship mode</dt>
            <dd>{humanize(po.ship_mode)}</dd>
          </>
        ) : null}
      </dl>
      {po.notes && <div className="fl-exp__rationale" style={{ marginTop: 7 }}>{po.notes}</div>}
      <div className="fl-gate__actions" style={{ marginTop: 9 }}>
        {pendingApprovalId ? (
          <button
            type="button"
            className="fl-btn fl-btn--primary fl-btn--sm"
            onClick={() => decideApproval(pendingApprovalId, true)}
          >
            Approve PO
          </button>
        ) : (
          <span className={`fl-pill fl-pill--${po.status === "approved" || po.status === "sent" ? "secured" : "watch"}`}>
            <span className={`fl-dot fl-dot--${po.status === "approved" || po.status === "sent" ? "secured" : "watch"}`} />
            {humanize(po.status)}
          </span>
        )}
      </div>
    </div>
  );
}

function VerifyCard({ verify }: { verify: VerifyResult }) {
  return (
    <div className="fl-card" style={{ borderColor: verify.gap_closed ? "rgba(74,222,128,0.35)" : "rgba(255,92,92,0.35)" }}>
      <div className="fl-card__head">
        <span className={`fl-dot fl-dot--${verify.gap_closed ? "secured" : "risk"}`} />
        <span className="fl-card__title">{verify.gap_closed ? "Coverage gap closed" : "Gap remains open"}</span>
        <span className="fl-panel__meta" style={{ marginLeft: "auto" }}>
          margin {verify.margin_days >= 0 ? "+" : ""}{verify.margin_days}d
        </span>
      </div>
      <div className="fl-exp__rationale">{verify.summary}</div>
      <div className="fl-panel__meta" style={{ marginTop: 7 }}>
        Residual risk: <span style={{ color: riskColor(verify.residual_risk.level) }}>{verify.residual_risk.level}</span>
      </div>
    </div>
  );
}

function LiveCall({ events }: { events: CallEvent[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const transcript = events.filter((e) => e.event === "transcript");
  const statuses = events.filter((e) => e.event === "status");
  const summary = [...events].reverse().find((e) => e.event === "summary")?.summary;
  const lastStatus = statuses[statuses.length - 1]?.status;
  const active = lastStatus === "connected" || lastStatus === "initiating" || lastStatus === "ringing";

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [transcript.length]);

  return (
    <div className="fl-call">
      <div className="fl-call__head">
        <span className={`fl-dot ${active ? "fl-dot--live" : "fl-dot--idle"}`} />
        <span className={`fl-call__status ${active ? "fl-call__live" : ""}`}>
          {lastStatus ? humanize(lastStatus) : "—"}
        </span>
        {active && (
          <div className="fl-wave" aria-hidden>
            <span /><span /><span /><span /><span />
          </div>
        )}
        {active && <span className="fl-call__status fl-call__live" style={{ marginLeft: "auto" }}>AI agent on call</span>}
      </div>

      {transcript.length ? (
        <div className="fl-transcript" ref={ref}>
          {transcript.map((e, i) => (
            <div key={i} className={`fl-line fl-line--${e.speaker === "supplier" ? "supplier" : "agent"}`}>
              <span className="fl-line__who">{e.speaker === "supplier" ? "Supplier" : "Faultline agent"}</span>
              <span className="fl-line__text">{e.text}</span>
            </div>
          ))}
        </div>
      ) : (
        <Empty>connecting…</Empty>
      )}

      {summary && (
        <div className="fl-call__summary">
          <span className={`fl-dot fl-dot--${summary.agreed ? "secured" : "watch"}`} />
          {summary.agreed ? "Agreed" : "No agreement"}
          {summary.unit_price_usd != null && <span className="fl-num">· ${summary.unit_price_usd.toFixed(2)}/unit</span>}
          {summary.lead_time_days != null && <span className="fl-num">· {summary.lead_time_days}d lead</span>}
        </div>
      )}
    </div>
  );
}

function pendingApprovalFor(s: ReturnType<typeof useFaultline>, exposureId: string): string | undefined {
  const a = s.approval;
  if (!a) return undefined;
  if (s.approvalResolved[a.approval_id]) return undefined;
  if (a.context?.exposure_ids?.includes(exposureId)) return a.approval_id;
  return undefined;
}

function riskColor(level: string): string {
  return level === "high" ? "var(--risk)" : level === "medium" ? "var(--watch)" : "var(--secured)";
}

/** Where the map should fly when this exposure's row is clicked: the disruption
 *  epicenter (root-cause world-event), falling back to the chokepoint supplier. */
function focusForExposure(s: ReturnType<typeof useFaultline>, e: Exposure): FocusDetail | null {
  const ev = s.eventsById[e.root_cause_event_id];
  if (ev?.location) {
    return { lat: ev.location.lat, lon: ev.location.lon, label: e.product_name, url: ev.url };
  }
  const path = s.exposurePaths.find((p) => e.path_ids?.includes(p.path_id));
  const node =
    path?.supplier_chain.find((n) => n.supplier_id === e.chokepoint_supplier_id) ?? path?.supplier_chain[0];
  if (node?.location) {
    return { lat: node.location.lat, lon: node.location.lon, label: e.product_name };
  }
  return null;
}

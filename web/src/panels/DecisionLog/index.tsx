/** Decision Log — the agent's narrative, every conclusion linked to live evidence (UI prompt 5).
 *  Header zone: the generated Situation Report (headline metric + download via GET /report/{run_id}).
 *  Timeline: timestamped entries; each entry's evidence chips cite source world-events
 *  ("GDACS · 08:42") and link to the source URL.
 *  Session C2 owns this folder. */
import { EvidenceChip, Empty } from "../_shared/ui";
import { AccordionPanel } from "../_shared/accordion";
import { useFaultline } from "../_shared/store";
import { reportUrl } from "../../lib/api";
import { clock, humanize } from "../_shared/format";

export default function DecisionLog() {
  const s = useFaultline();
  const decisions = s.decisions;

  const strip = decisions.length ? (
    <>
      <b>{decisions.length}</b> entries
      {s.brief ? <> · <span style={{ color: "var(--secured)" }}>report ready</span></> : null}
    </>
  ) : (
    <>awaiting reasoning</>
  );

  return (
    <AccordionPanel
      id="decision"
      title="Decision Log"
      meta={decisions.length ? `${decisions.length} entries` : undefined}
      strip={strip}
    >
      <ReportHeader />

      {decisions.length ? (
        <div className="fl-timeline">
          {decisions.map((d) => (
            <div className="fl-entry fl-enter" key={d.decision_id}>
              <div className="fl-entry__time">{clock(d.ts)}</div>
              <div className="fl-entry__body">
                <div className="fl-entry__title">
                  <span className="fl-entry__agent">{d.agent}</span>
                  <span>{humanize(d.kind)}</span>
                  {d.simulated && <span className="fl-sim-tag">Simulated</span>}
                </div>
                <div className="fl-entry__summary">{d.summary}</div>
                {d.evidence_event_ids?.length ? (
                  <div className="fl-entry__chips">
                    {d.evidence_event_ids.map((id) => (
                      <EvidenceChip key={id} eventId={id} event={s.eventsById[id]} />
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty>the agent's reasoning will appear here, step by step</Empty>
      )}
    </AccordionPanel>
  );
}

function ReportHeader() {
  const s = useFaultline();
  const brief = s.brief;
  const runId = brief?.run_id ?? s.runId ?? undefined;
  const ready = Boolean(brief);
  const href = ready && runId ? reportUrl(runId) : undefined;

  return (
    <div className="fl-report">
      <div className="fl-report__metric">
        <span className={`fl-report__value ${ready ? "fl-enter" : ""}`} key={brief?.report_id ?? "pending"}>
          {brief?.headline_metric?.value ?? "—"}
        </span>
        <span className="fl-report__label">{brief?.headline_metric?.label ?? "$ at risk averted"}</span>
      </div>
      <div className="fl-report__title">
        {brief?.title ?? "Situation report generates once the run completes."}
      </div>
      {ready && href ? (
        <a className="fl-btn fl-btn--sm" href={href} target="_blank" rel="noreferrer" download>
          Download
        </a>
      ) : (
        <button type="button" className="fl-btn fl-btn--sm" disabled>
          Download
        </button>
      )}
    </div>
  );
}

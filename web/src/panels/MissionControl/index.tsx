/** Mission Control — the agent's reasoning, live (UI prompt 3).
 *  Current goal · numbered plan (active step amber) · streaming tool-call chips
 *  with Elastic MCP calls visually distinct · retrieved evidence · confidence ·
 *  the Approval-required gate card wired to approval.request / approval.decision.
 *  Session C2 owns this folder. Driven entirely by C1's replay/live ws stream. */
import { useEffect, useRef, useState } from "react";
import { EvidenceChip, Empty } from "../_shared/ui";
import { AccordionPanel } from "../_shared/accordion";
import { useFaultline, decideApproval, type PlanStep, type ToolCall } from "../_shared/store";
import { usd, pct, humanize } from "../_shared/format";
import { CountUp } from "../_shared/anim";

const CANONICAL_STEPS: { id: string; label: string }[] = [
  { id: "scan", label: "Scan world events" },
  { id: "trace", label: "Trace exposure paths" },
  { id: "assess", label: "Quantify exposure" },
  { id: "approve", label: "Approval gate" },
  { id: "resource", label: "Secure alternate supply" },
  { id: "verify", label: "Verify coverage" },
];

export default function MissionControl() {
  const s = useFaultline();
  const steps: PlanStep[] = s.plan?.steps?.length
    ? s.plan.steps
    : CANONICAL_STEPS.map((x) => ({ ...x, status: "pending" as const }));

  const goal = deriveGoal(s);
  const confidence = deriveConfidence(s);
  const step = s.plan?.active_step ?? null;
  const explicitlyResolved = s.approval ? s.approvalResolved[s.approval.approval_id] : undefined;
  // The live gate shows only while the plan sits on the approval step. Once the run
  // advances (or the operator decides), it collapses to a confirmation — so unattended
  // replay (where C1's harness drops the scripted decision) stays coherent.
  const gateActive = step === "approve" && !explicitlyResolved;
  const pending = s.approval && gateActive ? s.approval : null;
  let resolved: { approved: boolean; note?: string } | null = null;
  if (s.approval && !gateActive) resolved = explicitlyResolved ?? { approved: true };

  const meta = `mode ${deriveMode(s)}`;
  const activeLabel = steps.find((x) => x.status === "active")?.label;
  const stripPhase = activeLabel ?? (steps.every((x) => x.status === "done") ? "Run complete" : "Idle");
  const strip = (
    <>
      <b>{stripPhase}</b>
      {pending ? <span className="risk"> · approval required</span> : null}
      {s.toolCalls.length ? ` · ${s.toolCalls.length} calls` : ""}
    </>
  );

  return (
    <AccordionPanel id="mission" title="Mission Control" meta={meta} strip={strip}>
      {/* approval gate floats to the top when pending, so the gate is unmissable */}
      {pending && (
        <div style={{ marginBottom: 13 }}>
          <ApprovalGate
            approvalId={pending.approval_id}
            summary={pending.summary}
            dollars={pending.context?.dollars_at_risk_total_usd}
            actionKind={pending.action_kind}
          />
        </div>
      )}

      {/* current goal */}
      <div style={{ marginBottom: 12 }}>
        <div className="fl-eyebrow">Current goal</div>
        <div style={{ fontSize: 15, lineHeight: 1.35, marginTop: 3 }}>{goal}</div>
      </div>

      {/* numbered live plan */}
      <div className="fl-eyebrow" style={{ marginBottom: 5 }}>Plan</div>
      <ol className="fl-plan" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {steps.map((step, i) => (
          <li key={step.id} className={`fl-step fl-step--${step.status}`}>
            <span className="fl-step__no">{i + 1}</span>
            <span className={`fl-step__tick ${step.status === "pending" ? "fl-step__tick--idle" : ""}`}>
              {step.status === "done" ? "✓" : step.status === "active" ? "▸" : step.status === "error" ? "✕" : "·"}
            </span>
            <span className="fl-step__label">{step.label}</span>
          </li>
        ))}
      </ol>

      {/* streaming tool-call chips */}
      <div className="fl-eyebrow" style={{ margin: "13px 0 5px" }}>
        Tool calls{s.toolCalls.length ? ` · ${s.toolCalls.length}` : ""}
      </div>
      <ToolStream calls={s.toolCalls} />

      {/* retrieved evidence + confidence */}
      <div style={{ display: "flex", gap: 14, marginTop: 13, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="fl-eyebrow" style={{ marginBottom: 5 }}>Retrieved evidence</div>
          {s.relevantEvents.length ? (
            <div className="fl-entry__chips">
              {s.relevantEvents.map((e) => (
                <EvidenceChip key={e.event_id} eventId={e.event_id} event={e} />
              ))}
            </div>
          ) : (
            <Empty>none yet</Empty>
          )}
        </div>
        <div style={{ width: 116, flex: "0 0 auto" }}>
          <div className="fl-eyebrow" style={{ marginBottom: 5 }}>Confidence</div>
          <div className="fl-meter">
            <div className="fl-meter__fill" style={{ width: pct(confidence) }} />
          </div>
          <div className="fl-num" style={{ fontSize: 11, color: "var(--ink-dim)", marginTop: 3 }}>{pct(confidence)}</div>
        </div>
      </div>

      {resolved && (
        <div className="fl-gate fl-gate--resolved" style={{ marginTop: 13 }}>
          <div className="fl-gate__eyebrow" style={{ color: resolved.approved ? "var(--secured)" : "var(--risk)" }}>
            <span className={`fl-dot fl-dot--${resolved.approved ? "secured" : "risk"}`} />
            {resolved.approved ? "Approved" : "Rejected"}
          </div>
          {resolved.note && <div className="fl-gate__summary fl-dim">“{resolved.note}”</div>}
        </div>
      )}
    </AccordionPanel>
  );
}

function ToolStream({ calls }: { calls: ToolCall[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [calls.length, calls[calls.length - 1]?.status]);

  if (!calls.length) return <Empty>awaiting the first tool call…</Empty>;
  const recent = calls.slice(-12);
  return (
    <div className="fl-tools" ref={ref}>
      {recent.map((c) => (
        <div key={c.call_id} className={`fl-tool fl-enter ${c.elastic ? "fl-tool--elastic" : ""}`}>
          <span className={`fl-dot ${dotClass(c.status)}`} />
          {c.elastic && <span className="fl-tool__badge">Elastic</span>}
          <span className="fl-tool__name">{c.tool}</span>
          <span className="fl-tool__args">{c.args_summary}</span>
          {c.status === "ok" && c.latency_ms != null && <span className="fl-tool__lat">{c.latency_ms}ms</span>}
          {c.status === "err" && <span className="fl-tool__lat" style={{ color: "var(--risk)" }}>err</span>}
        </div>
      ))}
    </div>
  );
}

function ApprovalGate({
  approvalId,
  summary,
  dollars,
  actionKind,
}: {
  approvalId: string;
  summary: string;
  dollars?: number;
  actionKind: string;
}) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");

  return (
    <div className="fl-gate">
      <div className="fl-gate__eyebrow">
        <span className="fl-dot fl-dot--live" />
        Approval required · {humanize(actionKind)}
      </div>
      <div className="fl-gate__summary">{summary}</div>
      {dollars != null && (
        <div>
          <span className="fl-gate__metric"><CountUp value={dollars} format={usd} /></span>
          <span className="fl-eyebrow" style={{ marginLeft: 8 }}>at risk</span>
        </div>
      )}
      {editing && (
        <textarea
          className="fl-gate__note"
          placeholder="Add a note or instruction for the agent…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          autoFocus
        />
      )}
      <div className="fl-gate__actions">
        <button
          type="button"
          className="fl-btn fl-btn--primary"
          onClick={() => decideApproval(approvalId, true, note.trim() || undefined)}
        >
          {editing ? "Approve with note" : "Approve"}
        </button>
        {!editing ? (
          <button type="button" className="fl-btn" onClick={() => setEditing(true)}>
            Edit
          </button>
        ) : (
          <button type="button" className="fl-btn" onClick={() => setEditing(false)}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

function dotClass(status: ToolCall["status"]): string {
  if (status === "ok") return "fl-dot--secured";
  if (status === "err") return "fl-dot--risk";
  return "fl-dot--live";
}

function deriveGoal(s: ReturnType<typeof useFaultline>): string {
  if (s.brief?.title) return s.brief.title;
  const top = [...s.exposures].sort((a, b) => a.rank - b.rank)[0];
  if (top && top.status === "at_risk") {
    return `Protect ${top.product_name} — ${usd(top.dollars_at_risk_usd)} of revenue exposed`;
  }
  if (s.status?.note) return s.status.note;
  return "Monitoring the global supplier graph for disruption";
}

/** The header status (seq 0) can land before this panel subscribes in replay, so
 *  infer the mode from the run's data when no status message is in hand: any
 *  simulated:true artifact ⇒ simulated; an active/known run ⇒ live; else standby. */
function deriveMode(s: ReturnType<typeof useFaultline>): string {
  if (s.status) return s.status.mode;
  const simulated =
    s.exposures.some((e) => e.simulated) || s.decisions.some((d) => d.simulated);
  if (simulated) return "simulated";
  if (s.runId || s.plan) return "live";
  return "standby";
}

function deriveConfidence(s: ReturnType<typeof useFaultline>): number | undefined {
  if (s.exposures.length) {
    return Math.max(...s.exposures.map((e) => e.severity));
  }
  if (s.exposurePaths.length) {
    return Math.max(...s.exposurePaths.map((p) => p.match.score));
  }
  return undefined;
}

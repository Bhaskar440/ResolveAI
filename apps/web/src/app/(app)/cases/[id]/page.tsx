import Link from "next/link";
import { ComplaintThread } from "@/components/ComplaintThread";
import { DisputeActions } from "@/components/DisputeActions";
import { LiveRefresh } from "@/components/LiveRefresh";
import {
  AgentDot,
  ConfidenceBar,
  formatMoney,
  PageHeader,
  Panel,
  ReasonBadge,
  StatusBadge,
  utc,
} from "@/components/ui";
import {
  ApiError,
  getDispute,
  getRun,
  getSystemStatus,
  type DisputeDetail,
  type PolicyEval,
  type RunDetail,
  type SystemStatus,
} from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const STEP_STYLE: Record<string, string> = {
  llm: "border-emerald-900 bg-emerald-950/50 text-emerald-300",
  fallback: "border-amber-900 bg-amber-950/50 text-amber-300",
  policy: "border-sky-900 bg-sky-950/50 text-sky-300",
  plan: "border-violet-900 bg-violet-950/50 text-violet-300",
  counter: "border-orange-900 bg-orange-950/50 text-orange-300",
  retrieval: "border-cyan-900 bg-cyan-950/50 text-cyan-300",
  execution: "border-emerald-900 bg-emerald-950/50 text-emerald-300",
  noop: "border-slate-800 bg-slate-900 text-slate-400",
};

function StepBadge({ type }: { type: string }) {
  const cls = STEP_STYLE[type] ?? "border-slate-800 bg-slate-900 text-slate-400";
  return (
    <span className={`mono rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wider ${cls}`}>
      {type}
    </span>
  );
}

function Fact({ label, value, mono = true }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[9px] uppercase tracking-[0.12em] text-slate-500">{label}</dt>
      <dd className={`mt-0.5 text-[11.5px] text-slate-200 ${mono ? "mono" : ""}`}>{value || "—"}</dd>
    </div>
  );
}

function PolicyCard({ policy }: { policy: PolicyEval }) {
  const env = (policy.envelope ?? {}) as {
    pre?: {
      allowed_actions?: string[];
      max_amount?: string;
      partial_band?: [string, string];
      requires_approval?: boolean;
    };
    final?: { requires_approval?: boolean; max_amount?: string; max_auto_amount?: string };
  };
  const pre = env.pre ?? {};
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11.5px] font-medium text-slate-200">Deterministic policy gate</p>
        <span className="mono text-[9px] uppercase tracking-wider text-slate-500">
          rules v{policy.ruleset_version} · {policy.result}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(pre.allowed_actions ?? []).map((action) => (
          <span
            key={action}
            className="mono rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[9px] text-slate-300"
          >
            {action}
          </span>
        ))}
        {!pre.allowed_actions?.length && (
          <span className="mono text-[10px] text-slate-600">no envelope recorded</span>
        )}
      </div>
      <dl className="mono mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[9px] text-slate-500">
        <span>max {formatMoney(pre.max_amount ?? null)}</span>
        {pre.partial_band && (
          <span>
            band {formatMoney(pre.partial_band[0])}–{formatMoney(pre.partial_band[1])}
          </span>
        )}
        <span>auto {formatMoney(env.final?.max_auto_amount ?? null)}</span>
      </dl>
      <ul className="mt-3 space-y-2 border-t border-slate-800 pt-3">
        {(policy.matched_rules ?? []).map((rule) => (
          <li key={rule.id} className="text-[11px] leading-relaxed">
            <span className="mono text-slate-300">{rule.id}</span>{" "}
            <span
              className={`mono text-[9px] uppercase ${
                rule.outcome === "allow"
                  ? "text-emerald-400"
                  : rule.outcome === "require_approval"
                    ? "text-amber-400"
                    : "text-rose-400"
              }`}
            >
              {rule.outcome}
            </span>
            <p className="text-slate-500">{rule.reason}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PaymentPanel({ detail }: { detail: DisputeDetail }) {
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-slate-800 bg-[#0a1019] p-3">
        <div className="flex items-center justify-between gap-3">
          <p className="mono text-[9px] uppercase tracking-wider text-slate-500">PayPal order</p>
          <span className="mono rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[9px] uppercase text-slate-300">
            {detail.order?.status ?? "not linked"}
          </span>
        </div>
        <p className="mono mt-1.5 break-all text-[10px] text-slate-400">
          {detail.order?.paypal_order_id ?? "—"}
        </p>
        <div className="mt-2 flex items-end justify-between gap-3">
          <span className="text-[11px] text-slate-400">{detail.order?.item_title ?? "No item title"}</span>
          <span className="mono text-[12px] text-slate-100">
            {formatMoney(detail.order?.amount ?? null, detail.order?.currency)}
          </span>
        </div>
      </div>

      <div className="rounded-lg border border-slate-800 bg-[#0a1019] p-3">
        <div className="flex items-center justify-between gap-3">
          <p className="mono text-[9px] uppercase tracking-wider text-slate-500">Capture</p>
          <span
            className={`mono rounded border px-1.5 py-0.5 text-[9px] uppercase ${
              detail.capture?.status === "COMPLETED"
                ? "border-emerald-800 bg-emerald-950/50 text-emerald-300"
                : "border-amber-800 bg-amber-950/50 text-amber-300"
            }`}
          >
            {detail.capture?.status ?? "none"}
          </span>
        </div>
        <p className="mono mt-1.5 break-all text-[10px] text-slate-400">
          {detail.capture?.paypal_capture_id ?? "—"}
        </p>
        <div className="mono mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[9px] text-slate-500">
          <span>{formatMoney(detail.capture?.amount ?? null, detail.capture?.currency)}</span>
          <span>seller protection {detail.capture?.seller_protection_status ?? "UNKNOWN"}</span>
        </div>
      </div>

      <div className="rounded-lg border border-slate-800 bg-[#0a1019] p-3">
        <div className="flex items-center justify-between gap-3">
          <p className="mono text-[9px] uppercase tracking-wider text-slate-500">Refund receipts</p>
          <span className="mono text-[9px] text-slate-600">{detail.refunds.length} receipt(s)</span>
        </div>
        {detail.refunds.length === 0 ? (
          <p className="mt-2 text-[11px] text-slate-500">No refund has been issued for this case.</p>
        ) : (
          <div className="mt-2 space-y-2">
            {detail.refunds.map((refund) => (
              <div key={refund.id} className="rounded border border-slate-800/80 bg-slate-900/30 p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="mono text-[11px] text-slate-200">
                    {formatMoney(refund.amount, refund.currency)}
                  </span>
                  <span
                    className={`mono rounded border px-1.5 py-0.5 text-[8px] uppercase tracking-wider ${
                      refund.simulated
                        ? "border-amber-800 bg-amber-950/50 text-amber-300"
                        : "border-emerald-800 bg-emerald-950/50 text-emerald-300"
                    }`}
                  >
                    {refund.simulated ? "simulated (replay)" : "live paypal"}
                  </span>
                </div>
                <p className="mono mt-1 break-all text-[9px] text-slate-500">{refund.paypal_refund_id}</p>
                <p className="mono mt-0.5 text-[9px] text-slate-600">
                  {refund.status} · by {refund.initiated_by} · {utc(refund.created_at)}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default async function CaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let status: SystemStatus | null = null;
  let detail: DisputeDetail | null = null;
  let run: RunDetail | null = null;
  let error: string | null = null;

  try {
    status = await getSystemStatus();
    detail = await getDispute(id);
    if (detail.latest_run) {
      run = await getRun(detail.latest_run.id);
    }
  } catch (err) {
    error = err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err);
  }

  if (error || !detail) {
    return (
      <div className="mx-auto max-w-3xl py-16">
        <Link href="/cases" className="mono text-[11px] text-slate-500 hover:text-slate-300">
          ← back to case queue
        </Link>
        <div className="mt-6 rounded-xl border border-rose-900/60 bg-rose-950/30 p-6">
          <p className="mono text-[10px] uppercase tracking-wider text-rose-300">case unavailable</p>
          <p className="mt-2 text-sm text-rose-100">{error ?? "Dispute not found."}</p>
        </div>
      </div>
    );
  }

  const dispute = detail.dispute;
  const decision = detail.decision;
  const pending = detail.approvals.find((approval) => approval.status === "pending") ?? null;
  const canRun = !["RESOLVED", "AWAITING_APPROVAL"].includes(dispute.status);
  const runSeconds =
    run?.run.started_at && run?.run.ended_at
      ? ((new Date(run.run.ended_at).getTime() - new Date(run.run.started_at).getTime()) / 1000).toFixed(1)
      : null;
  const activeRun = dispute.status === "ANALYZING" || run?.run.status === "RUNNING";
  const mode = status?.mode ?? "offline";

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Link href="/cases" className="mono text-[10px] text-slate-500 hover:text-slate-300">
          ← case queue
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <LiveRefresh active={activeRun} />
          <span className="mono text-[9px] uppercase tracking-wider text-slate-600">
            {mode} mode · {dispute.paypal_status}
          </span>
        </div>
      </div>

      <PageHeader
        eyebrow={`Case ${dispute.paypal_case_number ?? dispute.paypal_dispute_id}`}
        title={dispute.paypal_case_number ?? dispute.paypal_dispute_id}
        description={dispute.reason_detail ?? dispute.agent_summary ?? "No buyer narrative recorded."}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ReasonBadge reason={dispute.reason_code} />
            <StatusBadge status={dispute.status} />
            {pending && (
              <span className="mono rounded border border-amber-800 bg-amber-950/50 px-2 py-0.5 text-[9px] uppercase tracking-wider text-amber-300">
                approval pending
              </span>
            )}
          </div>
        }
      />

      <section className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card rounded-xl px-4 py-3.5">
          <p className="mono text-[9px] uppercase tracking-[0.16em] text-slate-500">Disputed amount</p>
          <p className="mono mt-1.5 text-[24px] font-semibold leading-none text-slate-50">
            {formatMoney(dispute.amount, dispute.currency)}
          </p>
          <div className="mt-2">{dispute.confidence && <ConfidenceBar value={dispute.confidence} />}</div>
        </div>
        <div className="card rounded-xl px-4 py-3.5">
          <p className="mono text-[9px] uppercase tracking-[0.16em] text-slate-500">Buyer</p>
          <p className="mt-1.5 text-[13px] text-slate-200">{dispute.buyer_label ?? "—"}</p>
          <p className="mono mt-1 text-[9px] text-slate-600">{dispute.reason_code}</p>
        </div>
        <div className="card rounded-xl px-4 py-3.5">
          <p className="mono text-[9px] uppercase tracking-[0.16em] text-slate-500">Response due</p>
          <p className="mono mt-1.5 text-[12px] text-slate-200">{utc(dispute.response_due_by)}</p>
          <p className="mono mt-1 text-[9px] text-slate-600">stage {dispute.lifecycle_stage}</p>
        </div>
        <div className="card rounded-xl px-4 py-3.5">
          <p className="mono text-[9px] uppercase tracking-[0.16em] text-slate-500">Latest run</p>
          <p className="mt-1.5 text-[12px] text-slate-200">
            {run ? `${run.run.status} · ${run.run.iterations} round(s)` : "not run yet"}
          </p>
          <p className="mono mt-1 text-[9px] text-slate-600">
            {run ? `${run.run.output_tokens} tokens · ${runSeconds ?? "—"}s` : "no agent transcript"}
          </p>
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.85fr)]">
        <div className="space-y-5">
          <Panel title="Customer complaint" subtitle="buyer messages + merchant case file">
            <ComplaintThread disputeId={dispute.id} messages={detail.messages} />
          </Panel>

          <Panel
            title="Live agent activity"
            subtitle="persisted run steps · granular payloads"
            right={
              run ? (
                <div className="mono flex flex-wrap items-center gap-2 text-[9px] text-slate-500">
                  <span className="uppercase tracking-wider text-slate-400">{run.run.status}</span>
                  <span>{run.run.output_tokens} tok</span>
                  <span>{run.run.model_primary ?? "deterministic"}</span>
                </div>
              ) : (
                <span className="mono text-[9px] text-slate-600">no run yet</span>
              )
            }
          >
            {!run ? (
              <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/20 px-4 py-8 text-center">
                <p className="text-[12px] text-slate-400">Nothing has been executed for this case.</p>
                <p className="mono mt-1 text-[9px] text-slate-600">
                  Run the agents to produce a typed transcript and a policy-gated decision.
                </p>
              </div>
            ) : (
              <>
                <ol className="space-y-4">
                  {run.steps.map((step) => (
                    <li key={step.seq} className="flex gap-3">
                      <AgentDot agent={step.agent} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="mono text-[9px] uppercase tracking-wider text-slate-400">
                            {String(step.seq).padStart(2, "0")} {step.agent}
                          </span>
                          <StepBadge type={step.step_type} />
                          <span className="mono text-[9px] text-slate-600">
                            {step.latency_ms ? `${step.latency_ms}ms` : ""}
                            {step.tokens ? ` · ${step.tokens} tok` : ""}
                          </span>
                        </div>
                        <p className="mt-1 text-[12px] leading-relaxed text-slate-200">{step.summary}</p>
                        {step.step_type === "fallback" && (
                          <p className="mono mt-1 text-[9px] text-amber-400/80">
                            deterministic fallback — the model did not answer; not presented as model output
                          </p>
                        )}
                        <details className="mt-1">
                          <summary className="mono cursor-pointer text-[9px] text-slate-600 hover:text-slate-400">
                            payload
                          </summary>
                          <pre className="mono mt-1 overflow-x-auto rounded border border-slate-800 bg-[#080d15] p-2 text-[9px] leading-relaxed text-slate-400">
                            {JSON.stringify(step.payload, null, 2)}
                          </pre>
                        </details>
                      </div>
                    </li>
                  ))}
                </ol>

                {run.messages.length > 0 && (
                  <div className="mt-5 border-t border-slate-800 pt-4">
                    <h3 className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                      Agent transcript
                    </h3>
                    <div className="mt-3 space-y-3">
                      {run.messages.map((message) => (
                        <div key={message.seq} className="rounded-lg border border-slate-800/80 bg-[#0a1019] p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="mono text-[9px] uppercase tracking-wider text-slate-400">
                              {message.from_agent} → {message.to_agent}
                            </span>
                            <span className="mono rounded border border-slate-800 px-1.5 py-0.5 text-[8px] uppercase text-slate-500">
                              {message.msg_type}
                            </span>
                            {message.confidence && (
                              <span className="mono text-[8px] text-slate-500">
                                conf {Math.round(Number(message.confidence) * 100)}%
                              </span>
                            )}
                          </div>
                          <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-200">{message.claim}</p>
                          {message.rationale && (
                            <p className="mt-1 text-[10.5px] leading-relaxed text-slate-500">{message.rationale}</p>
                          )}
                          {message.evidence_refs.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {message.evidence_refs.slice(0, 8).map((ref) => (
                                <span key={ref} className="mono rounded bg-slate-900 px-1.5 py-0.5 text-[8px] text-slate-500">
                                  {ref}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </Panel>

          <Panel title="Case facts" subtitle="order, capture and seller protection">
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Fact label="Order" value={detail.order?.paypal_order_id} />
              <Fact label="Item" value={detail.order?.item_title ?? "—"} mono={false} />
              <Fact label="Order amount" value={formatMoney(detail.order?.amount ?? null, detail.order?.currency)} />
              <Fact label="Capture" value={detail.capture?.paypal_capture_id} />
              <Fact label="Capture status" value={detail.capture?.status} />
              <Fact
                label="Seller protection"
                value={
                  <span className={detail.capture?.seller_protection_status === "ELIGIBLE" ? "text-emerald-300" : "text-amber-300"}>
                    {detail.capture?.seller_protection_status ?? "UNKNOWN"}
                  </span>
                }
              />
            </dl>
          </Panel>

          {detail.policy && (
            <Panel title="Evidence & policy" subtitle="deterministic gate + retrieval citations">
              <PolicyCard policy={detail.policy} />
              {decision && decision.policy_citations.length > 0 && (
                <div className="mt-4 border-t border-slate-800 pt-4">
                  <p className="mono text-[9px] uppercase tracking-wider text-slate-500">Retrieved policy clauses</p>
                  <div className="mt-2 space-y-3">
                    {decision.policy_citations.map((citation) => (
                      <div key={citation.chunk_id} className="rounded-lg border border-slate-800/80 bg-[#0a1019] p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-[11px] font-medium text-slate-200">
                            {citation.document} · {citation.section}
                          </p>
                          <span className="mono rounded border border-cyan-900/60 bg-cyan-950/30 px-1.5 py-0.5 text-[8px] uppercase tracking-wider text-cyan-300">
                            score {citation.score.toFixed(3)}
                          </span>
                        </div>
                        <p className="mt-1 text-[10.5px] leading-relaxed text-slate-400">{citation.text}</p>
                        <p className="mono mt-1.5 text-[8.5px] text-slate-600">
                          {citation.source} · {citation.chunk_id} · {citation.retrieval_mode} · {citation.embedding_model}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Panel>
          )}
        </div>

        <aside className="space-y-5">
          <Panel
            title="AI resolution recommendation"
            subtitle="decision + confidence + reasoning"
            right={<span className="mono text-[9px] uppercase tracking-wider text-slate-500">{decision?.status ?? "none"}</span>}
          >
            {decision ? (
              <>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="mono text-[16px] font-semibold text-slate-50">{decision.decision_code}</span>
                  <span className="mono text-[15px] text-slate-200">
                    {formatMoney(decision.amount, decision.currency)}
                  </span>
                </div>
                <div className="mt-2">
                  <ConfidenceBar value={decision.confidence} />
                </div>
                <p className="mt-3 text-[11.5px] leading-relaxed text-slate-400">{decision.rationale}</p>
                {decision.reasoning && (
                  <details className="mt-3 border-t border-slate-800 pt-3">
                    <summary className="mono cursor-pointer text-[9px] uppercase tracking-wider text-slate-500 hover:text-slate-300">
                      full reasoning
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap text-[10.5px] leading-relaxed text-slate-400">
                      {decision.reasoning}
                    </p>
                  </details>
                )}
                {decision.missing_evidence.length > 0 && (
                  <div className="mt-3 border-t border-slate-800 pt-3">
                    <p className="mono text-[9px] uppercase tracking-wider text-amber-500/80">evidence still missing</p>
                    <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[10.5px] text-slate-400">
                      {decision.missing_evidence.map((gap) => (
                        <li key={gap}>{gap}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {decision.cited_evidence.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1 border-t border-slate-800 pt-3">
                    {decision.cited_evidence.slice(0, 10).map((ref) => (
                      <span key={ref} className="mono rounded bg-slate-900 px-1.5 py-0.5 text-[8px] text-slate-500">
                        {ref}
                      </span>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="text-[11.5px] leading-relaxed text-slate-500">
                No decision recorded yet. Run the agents to generate a recommendation inside the policy envelope.
              </p>
            )}
          </Panel>

          <Panel title="Merchant controls" subtitle="approval / rejection is real">
            <DisputeActions disputeId={dispute.id} canRun={canRun} approvalId={pending?.id ?? null} />
            {!canRun && (
              <p className="mono mt-3 text-[9px] leading-relaxed text-slate-600">
                {dispute.status === "RESOLVED"
                  ? "case resolved — the executor is idempotent and will not pay twice"
                  : "waiting for a human decision on the pending approval"}
              </p>
            )}
          </Panel>

          <Panel title="PayPal transaction & refunds" subtitle="order → capture → refund">
            <PaymentPanel detail={detail} />
          </Panel>

          {run && (
            <Panel title="Run metadata" subtitle="what was measured">
              <dl className="mono space-y-1.5 text-[9px]">
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">run</dt>
                  <dd className="text-slate-400">{run.run.id.slice(0, 8)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">trigger</dt>
                  <dd className="text-slate-400">{run.run.trigger}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">tokens</dt>
                  <dd className="text-slate-400">{run.run.output_tokens}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">started</dt>
                  <dd className="text-slate-400">{utc(run.run.started_at)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">ended</dt>
                  <dd className="text-slate-400">{utc(run.run.ended_at)}</dd>
                </div>
              </dl>
              {run.run.error_detail && (
                <p className="mono mt-3 rounded border border-rose-900/60 bg-rose-950/30 p-2 text-[9px] text-rose-300">
                  {run.run.error_code}: {run.run.error_detail}
                </p>
              )}
            </Panel>
          )}
        </aside>
      </div>
    </>
  );
}

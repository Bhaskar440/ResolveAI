import Link from "next/link";
import { DisputeActions } from "@/components/DisputeActions";
import { Nav } from "@/components/Nav";
import { AgentDot, ConfidenceBar, formatMoney, ReasonBadge, StatusBadge, utc } from "@/components/ui";
import {
  ApiError,
  getDispute,
  getRun,
  getSystemStatus,
  type DisputeDetail,
  type PolicyEval,
  type RunDetail,
} from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function Fact({ label, value, mono = true }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className={`mt-0.5 text-[12px] text-slate-200 ${mono ? "mono" : ""}`}>{value || "—"}</dd>
    </div>
  );
}

const STEP_STYLE: Record<string, string> = {
  llm: "border-emerald-900 bg-emerald-950/50 text-emerald-300",
  fallback: "border-amber-900 bg-amber-950/50 text-amber-300",
  policy: "border-sky-900 bg-sky-950/50 text-sky-300",
  plan: "border-violet-900 bg-violet-950/50 text-violet-300",
  counter: "border-orange-900 bg-orange-950/50 text-orange-300",
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
    <div className="card rounded-xl p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[13px] font-medium text-slate-200">Policy gate</h2>
        <span className="mono text-[10px] uppercase tracking-wider text-slate-500">
          rules v{policy.ruleset_version} · {policy.result}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {(pre.allowed_actions ?? []).map((a) => (
          <span
            key={a}
            className="mono rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300"
          >
            {a}
          </span>
        ))}
        {!pre.allowed_actions?.length && (
          <span className="mono text-[10px] text-slate-600">no envelope recorded</span>
        )}
      </div>

      <dl className="mono mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[10px] text-slate-500">
        <span>max {formatMoney(pre.max_amount ?? null)}</span>
        {pre.partial_band && (
          <span>
            band {formatMoney(pre.partial_band[0])}–{formatMoney(pre.partial_band[1])}
          </span>
        )}
        <span>auto {formatMoney(env.final?.max_auto_amount ?? null)}</span>
      </dl>

      <ul className="mt-4 space-y-2 border-t border-slate-800 pt-3">
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
      <p className="mt-3 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
        Deterministic, evaluated twice: once to constrain the Resolution agent (provisional
        confidence), once with the decision&apos;s real confidence.
      </p>
    </div>
  );
}

export default async function DisputePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let status = null as Awaited<ReturnType<typeof getSystemStatus>> | null;
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

  const live = Boolean(status?.capabilities.live_paypal);
  const mode = status?.mode ?? "offline";

  if (error || !detail) {
    return (
      <div className="min-h-screen">
        <Nav mode={mode} live={live} />
        <main className="mx-auto max-w-3xl px-6 py-16">
          <Link href="/" className="mono text-[11px] text-slate-500 hover:text-slate-300">
            ← back to queue
          </Link>
          <div className="mt-6 rounded-xl border border-rose-900/60 bg-rose-950/30 p-6">
            <p className="mono text-[10px] uppercase tracking-wider text-rose-300">
              case unavailable
            </p>
            <p className="mt-2 text-sm text-rose-100">{error ?? "Dispute not found."}</p>
          </div>
        </main>
      </div>
    );
  }

  const d = detail.dispute;
  const decision = detail.decision;
  const pending = detail.approvals.find((a) => a.status === "pending") ?? null;
  const canRun = !["RESOLVED", "AWAITING_APPROVAL"].includes(d.status);
  const runSeconds = run?.run.started_at && run?.run.ended_at
    ? (
        (new Date(run.run.ended_at).getTime() - new Date(run.run.started_at).getTime()) /
        1000
      ).toFixed(1)
    : null;

  return (
    <div className="min-h-screen">
      <Nav mode={mode} live={live} />

      <main className="mx-auto max-w-7xl px-6 pb-16 pt-6">
        <Link href="/" className="mono text-[11px] text-slate-500 hover:text-slate-300">
          ← back to queue
        </Link>

        <header className="mt-4 flex flex-wrap items-start justify-between gap-6 border-b border-slate-800/70 pb-6">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="mono text-[22px] font-semibold tracking-tight text-slate-50">
                {d.paypal_case_number ?? d.paypal_dispute_id}
              </h1>
              <ReasonBadge reason={d.reason_code} />
              <StatusBadge status={d.status} />
              {pending && (
                <span className="mono rounded border border-amber-800 bg-amber-950/50 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-300">
                  approval pending
                </span>
              )}
            </div>
            <p className="mt-2 max-w-2xl text-[12.5px] leading-relaxed text-slate-400">
              {d.reason_detail ?? d.agent_summary ?? "No buyer narrative recorded."}
            </p>
            <div className="mono mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[10px] text-slate-500">
              <span>buyer {d.buyer_label ?? "—"}</span>
              <span>paypal {d.paypal_status}</span>
              <span>stage {d.lifecycle_stage}</span>
              <span>due {utc(d.response_due_by)}</span>
            </div>
          </div>
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">disputed amount</p>
            <p className="mono mt-1 text-[28px] font-semibold leading-none text-slate-50">
              {formatMoney(d.amount, d.currency)}
            </p>
            {d.confidence && (
              <div className="mt-2 flex justify-end">
                <ConfidenceBar value={d.confidence} />
              </div>
            )}
          </div>
        </header>

        <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-5">
            <div className="card rounded-xl p-5">
              <h2 className="text-[13px] font-medium text-slate-200">Case facts</h2>
              <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
                <Fact label="Order" value={detail.order?.paypal_order_id} />
                <Fact label="Item" value={detail.order?.item_title ?? "—"} mono={false} />
                <Fact
                  label="Order amount"
                  value={formatMoney(detail.order?.amount ?? null, detail.order?.currency)}
                />
                <Fact label="Capture" value={detail.capture?.paypal_capture_id} />
                <Fact label="Capture status" value={detail.capture?.status} />
                <Fact
                  label="Seller protection"
                  value={
                    <span
                      className={
                        detail.capture?.seller_protection_status === "ELIGIBLE"
                          ? "text-emerald-300"
                          : "text-amber-300"
                      }
                    >
                      {detail.capture?.seller_protection_status ?? "UNKNOWN"}
                    </span>
                  }
                />
              </dl>
            </div>

            <div className="card rounded-xl p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-[13px] font-medium text-slate-200">Agent run</h2>
                {run ? (
                  <div className="mono flex flex-wrap items-center gap-3 text-[10px] text-slate-500">
                    <span className="uppercase tracking-wider text-slate-400">{run.run.status}</span>
                    <span>{run.run.iterations} round(s)</span>
                    <span>{run.run.output_tokens} tok</span>
                    <span>{runSeconds ? `${runSeconds}s` : "—"}</span>
                    <span>{run.run.model_primary ?? "deterministic"}</span>
                  </div>
                ) : (
                  <span className="mono text-[10px] text-slate-600">no run yet</span>
                )}
              </div>

              {!run && (
                <p className="mt-4 text-[12px] leading-relaxed text-slate-400">
                  Nothing has been executed for this case. Run the agents to produce a typed
                  transcript and a policy-gated decision.
                </p>
              )}

              {run && (
                <>
                  <ol className="mt-4 space-y-4">
                    {run.steps.map((step) => (
                      <li key={step.seq} className="flex gap-3">
                        <AgentDot agent={step.agent} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="mono text-[10px] uppercase tracking-wider text-slate-400">
                              {String(step.seq).padStart(2, "0")} {step.agent}
                            </span>
                            <StepBadge type={step.step_type} />
                            <span className="mono text-[10px] text-slate-600">
                              {step.latency_ms ? `${step.latency_ms}ms` : ""}
                              {step.tokens ? ` · ${step.tokens} tok` : ""}
                            </span>
                          </div>
                          <p className="mt-1 text-[12.5px] leading-relaxed text-slate-200">
                            {step.summary}
                          </p>
                          {step.step_type === "fallback" && (
                            <p className="mono mt-1 text-[10px] text-amber-400/80">
                              deterministic fallback — the model did not answer; this is not
                              presented as model output
                            </p>
                          )}
                          <details className="mt-1">
                            <summary className="mono cursor-pointer text-[10px] text-slate-600 hover:text-slate-400">
                              payload
                            </summary>
                            <pre className="mono mt-1 overflow-x-auto rounded border border-slate-800 bg-[#080d15] p-2 text-[10px] leading-relaxed text-slate-400">
                              {JSON.stringify(step.payload, null, 2)}
                            </pre>
                          </details>
                        </div>
                      </li>
                    ))}
                  </ol>

                  {run.messages.length > 0 && (
                    <div className="mt-5 border-t border-slate-800 pt-4">
                      <h3 className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                        Agent transcript
                      </h3>
                      <div className="mt-3 space-y-3">
                        {run.messages.map((m) => (
                          <div
                            key={m.seq}
                            className="rounded-lg border border-slate-800/80 bg-[#0a1019] p-3"
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="mono text-[10px] uppercase tracking-wider text-slate-400">
                                {m.from_agent} → {m.to_agent}
                              </span>
                              <span className="mono rounded border border-slate-800 px-1.5 py-0.5 text-[9px] uppercase text-slate-500">
                                {m.msg_type}
                              </span>
                              {m.confidence && (
                                <span className="mono text-[9px] text-slate-500">
                                  conf {Math.round(Number(m.confidence) * 100)}%
                                </span>
                              )}
                            </div>
                            <p className="mt-1.5 text-[12px] leading-relaxed text-slate-200">
                              {m.claim}
                            </p>
                            {m.rationale && (
                              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                                {m.rationale}
                              </p>
                            )}
                            {m.evidence_refs.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {m.evidence_refs.slice(0, 6).map((ref) => (
                                  <span
                                    key={ref}
                                    className="mono rounded bg-slate-900 px-1.5 py-0.5 text-[9px] text-slate-500"
                                  >
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
            </div>

            <div className="card rounded-xl p-5">
              <h2 className="text-[13px] font-medium text-slate-200">Buyer messages</h2>
              {detail.messages.length === 0 ? (
                <p className="mt-3 text-[12px] text-slate-500">
                  No messages were provided with this dispute — the agents reason from the dispute
                  reason and order facts only.
                </p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {detail.messages.map((m) => (
                    <li
                      key={m.id}
                      className={`rounded-lg border p-3 ${
                        m.direction === "inbound"
                          ? "border-slate-800 bg-[#0a1019]"
                          : "border-sky-900/50 bg-sky-950/20"
                      }`}
                    >
                      <div className="mono flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500">
                        <span>{m.author_type}</span>
                        <span>{utc(m.sent_at)}</span>
                      </div>
                      <p className="mt-1.5 text-[12px] leading-relaxed text-slate-300">{m.body}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {detail.policy && <PolicyCard policy={detail.policy} />}
          </div>

          <aside className="space-y-5">
            <div className="card rounded-xl p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-[13px] font-medium text-slate-200">Decision</h2>
                <span className="mono text-[10px] uppercase tracking-wider text-slate-500">
                  {decision?.status ?? "none"}
                </span>
              </div>
              {decision ? (
                <>
                  <div className="mt-3 flex items-baseline justify-between gap-2">
                    <span className="mono text-[15px] font-semibold text-slate-50">
                      {decision.decision_code}
                    </span>
                    <span className="mono text-[15px] text-slate-200">
                      {formatMoney(decision.amount, decision.currency)}
                    </span>
                  </div>
                  <div className="mt-2">
                    <ConfidenceBar value={decision.confidence} />
                  </div>
                  <p className="mt-3 text-[12px] leading-relaxed text-slate-400">
                    {decision.rationale}
                  </p>
                  {decision.policy_citations.length > 0 && (
                    <div className="mt-3 border-t border-slate-800 pt-3">
                      <p className="mono text-[9px] uppercase tracking-wider text-slate-500">
                        policy citations
                      </p>
                      <ul className="mt-2 space-y-2">
                        {decision.policy_citations.map((citation) => (
                          <li key={citation.chunk_id}>
                            <p className="text-[11px] font-medium text-slate-300">
                              {citation.document} · {citation.section}
                            </p>
                            <p className="mono mt-0.5 text-[9px] text-slate-600">
                              {citation.source} · {citation.chunk_id} · score{" "}
                              {citation.score.toFixed(3)} · {citation.retrieval_mode}
                            </p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {decision.missing_evidence.length > 0 && (
                    <div className="mt-3 border-t border-slate-800 pt-3">
                      <p className="mono text-[9px] uppercase tracking-wider text-amber-500/80">
                        evidence still missing
                      </p>
                      <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[11px] text-slate-400">
                        {decision.missing_evidence.map((gap) => (
                          <li key={gap}>{gap}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {decision.cited_evidence.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1 border-t border-slate-800 pt-3">
                      {decision.cited_evidence.slice(0, 8).map((ref) => (
                        <span
                          key={ref}
                          className="mono rounded bg-slate-900 px-1.5 py-0.5 text-[9px] text-slate-500"
                        >
                          {ref}
                        </span>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="mt-3 text-[12px] text-slate-500">No decision recorded yet.</p>
              )}
            </div>

            <div className="card rounded-xl p-5">
              <h2 className="text-[13px] font-medium text-slate-200">Actions</h2>
              <div className="mt-3">
                <DisputeActions disputeId={d.id} canRun={canRun} approvalId={pending?.id ?? null} />
              </div>
              {!canRun && (
                <p className="mono mt-3 text-[10px] leading-relaxed text-slate-600">
                  {d.status === "RESOLVED"
                    ? "case resolved — the executor is idempotent and will not pay twice"
                    : "waiting for a human decision on the pending approval"}
                </p>
              )}
            </div>

            {detail.refunds.length > 0 && (
              <div className="card rounded-xl p-5">
                <h2 className="text-[13px] font-medium text-slate-200">Refund receipts</h2>
                <div className="mt-3 space-y-3">
                  {detail.refunds.map((r) => (
                    <div key={r.id} className="rounded-lg border border-slate-800 bg-[#0a1019] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="mono text-[11px] text-slate-200">
                          {formatMoney(r.amount, r.currency)}
                        </span>
                        <span
                          className={`mono rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wider ${
                            r.simulated
                              ? "border-amber-800 bg-amber-950/50 text-amber-300"
                              : "border-emerald-800 bg-emerald-950/50 text-emerald-300"
                          }`}
                        >
                          {r.simulated ? "simulated (replay)" : "live paypal"}
                        </span>
                      </div>
                      <p className="mono mt-1 break-all text-[10px] text-slate-500">
                        {r.paypal_refund_id}
                      </p>
                      <p className="mono mt-1 text-[10px] text-slate-600">
                        {r.status} · by {r.initiated_by} · {utc(r.created_at)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {run && (
              <div className="card rounded-xl p-5">
                <h2 className="text-[13px] font-medium text-slate-200">Run metadata</h2>
                <dl className="mono mt-3 space-y-1.5 text-[10px]">
                  <div className="flex justify-between">
                    <dt className="text-slate-500">run</dt>
                    <dd className="text-slate-400">{run.run.id.slice(0, 8)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">trigger</dt>
                    <dd className="text-slate-400">{run.run.trigger}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">tokens</dt>
                    <dd className="text-slate-400">{run.run.output_tokens}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">started</dt>
                    <dd className="text-slate-400">{utc(run.run.started_at)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">ended</dt>
                    <dd className="text-slate-400">{utc(run.run.ended_at)}</dd>
                  </div>
                </dl>
                {run.run.error_detail && (
                  <p className="mono mt-3 rounded border border-rose-900/60 bg-rose-950/30 p-2 text-[10px] text-rose-300">
                    {run.run.error_code}: {run.run.error_detail}
                  </p>
                )}
              </div>
            )}
          </aside>
        </div>
      </main>
    </div>
  );
}

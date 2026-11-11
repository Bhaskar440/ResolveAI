import Link from "next/link";
import { ApprovalInbox } from "@/components/ApprovalInbox";
import { DisputeGrid } from "@/components/DisputeGrid";
import { RefreshButton } from "@/components/RefreshButton";
import {
  ApiError,
  getAnalytics,
  getMetrics,
  getPolicyRules,
  getSystemStatus,
  listApprovals,
  type Analytics,
  type Approval,
  type Metrics,
  type PolicyRules,
  type SystemStatus,
} from "@/lib/api";
import { formatMoney, Meter, PageHeader, Panel, reasonLabel } from "@/components/ui";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function Stat({
  label,
  value,
  hint,
  tone = "neutral",
  children,
}: {
  label: string;
  value: string;
  hint: string;
  tone?: "good" | "bad" | "warn" | "neutral";
  children?: React.ReactNode;
}) {
  const dot = {
    good: "bg-emerald-400",
    bad: "bg-rose-400",
    warn: "bg-amber-400",
    neutral: "bg-slate-500",
  }[tone];
  return (
    <div className="card rounded-xl p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        <span className="text-[9px] font-medium uppercase tracking-[0.18em] text-slate-400">{label}</span>
      </div>
      <div className="mt-3 text-[25px] font-semibold leading-none tracking-tight text-slate-100">{value}</div>
      <div className="mono mt-2 text-[9.5px] leading-relaxed text-slate-500">{hint}</div>
      {children}
    </div>
  );
}

async function load<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch {
    return null;
  }
}

export default async function Home() {
  const [status, metrics, approvals, rules, analytics] = await Promise.all([
    load<SystemStatus>(getSystemStatus()),
    load<Metrics>(getMetrics()),
    load<Approval[]>(listApprovals("pending")),
    load<PolicyRules>(getPolicyRules()),
    load<Analytics>(getAnalytics()),
  ]);

  let error: string | null = null;
  if (!metrics) {
    try {
      await getMetrics();
    } catch (err) {
      error = err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err);
    }
  }

  const approvalList = approvals ?? [];
  const totalReason = analytics?.by_reason.reduce((sum, row) => sum + row.count, 0) ?? 0;
  const reasonRows = (analytics?.by_reason ?? []).slice(0, 5);

  return (
    <>
      <PageHeader
        eyebrow="PayPal AI Hackathon · merchant operations"
        title="Merchant dashboard"
        description="Every number is queried from PostgreSQL on this request. The agents can only move money through a deterministic policy envelope and, above the cap, a human decision."
        actions={
          <>
            <RefreshButton label="Refresh live data" />
            <Link
              href="/cases"
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-[11px] font-medium text-slate-200 transition hover:border-slate-500 hover:bg-slate-800"
            >
              Open case queue →
            </Link>
          </>
        }
      />

      {error && (
        <section className="mb-5 rounded-xl border border-rose-900/60 bg-rose-950/30 p-5">
          <p className="mono text-[10px] uppercase tracking-wider text-rose-300">api unreachable</p>
          <p className="mt-2 text-sm text-rose-100">
            The dashboard will not invent numbers. Start the stack and refresh.
          </p>
          <pre className="mono mt-3 overflow-x-auto whitespace-pre-wrap text-[11px] leading-relaxed text-rose-300/80">
            {error}
          </pre>
        </section>
      )}

      {metrics && (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Open disputes"
              value={String(metrics.open_disputes)}
              tone={metrics.open_disputes > 0 ? "warn" : "good"}
              hint={`${metrics.awaiting_approval} awaiting approval · ${metrics.escalated} escalated`}
            />
            <Stat
              label="Exposure at risk"
              value={formatMoney(metrics.total_at_risk)}
              tone={Number(metrics.total_at_risk) > 0 ? "warn" : "good"}
              hint="sum of unresolved dispute amounts"
            >
              {analytics && (
                <div className="mt-3">
                  <Meter value={analytics.pending_cases} max={Math.max(1, analytics.total_disputes)} tone="amber" />
                </div>
              )}
            </Stat>
            <Stat
              label="Resolved cases"
              value={String(metrics.resolved)}
              tone="good"
              hint={
                analytics
                  ? `${analytics.resolution_rate}% resolution rate · ${metrics.auto_executed} autonomous / ${metrics.human_executed} human`
                  : `${metrics.auto_executed} autonomous · ${metrics.human_executed} human`
              }
            >
              {analytics && (
                <div className="mt-3">
                  <Meter value={analytics.resolved_cases} max={Math.max(1, analytics.total_disputes)} tone="emerald" />
                </div>
              )}
            </Stat>
            <Stat
              label="Refunded total"
              value={formatMoney(metrics.recovered)}
              tone="good"
              hint={
                analytics
                  ? `${analytics.refunds.completed} completed · ${analytics.refunds.simulated} simulated (replay)`
                  : "completed refund receipts"
              }
            />
          </section>

          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(330px,0.8fr)]">
            <div className="space-y-5">
              <Panel
                title="Needs a human decision"
                subtitle="above the autonomous cap · policy-gated"
                right={
                  <span className="mono rounded border border-amber-900/60 bg-amber-950/30 px-2 py-0.5 text-[9px] uppercase tracking-wider text-amber-300">
                    {approvalList.length} pending
                  </span>
                }
              >
                <ApprovalInbox approvals={approvalList} />
              </Panel>

              <Panel
                title="Dispute queue"
                subtitle="GET /api/v1/disputes · infinite row model"
                right={
                  <Link href="/cases" className="mono text-[9px] uppercase tracking-wider text-slate-500 hover:text-slate-300">
                    full case management →
                  </Link>
                }
              >
                <DisputeGrid heightClass="h-[440px]" compact />
              </Panel>

              <div className="grid gap-4 sm:grid-cols-2">
                <Panel title="Recent decisions" subtitle="latest resolved work">
                  <div className="space-y-2.5">
                    {(analytics?.by_reason ?? []).filter((row) => row.resolved > 0).length === 0 && (
                      <p className="text-[11.5px] text-slate-500">No resolved cases yet.</p>
                    )}
                    {(analytics?.by_reason ?? [])
                      .filter((row) => row.resolved > 0)
                      .slice(0, 4)
                      .map((row) => (
                        <div key={row.reason_code} className="flex items-center justify-between gap-3">
                          <span className="truncate text-[11px] text-slate-300">{reasonLabel(row.reason_code)}</span>
                          <span className="mono text-[10px] text-slate-500">
                            {row.resolved} · {formatMoney(row.refunded)}
                          </span>
                        </div>
                      ))}
                  </div>
                </Panel>
                <Panel title="Run health" subtitle="measured from persisted runs">
                  <dl className="space-y-2.5 text-[11px]">
                    <div className="flex justify-between gap-2">
                      <dt className="text-slate-500">Median run</dt>
                      <dd className="mono text-slate-200">{metrics.median_run_seconds ?? "—"}s</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-slate-500">Agent runs</dt>
                      <dd className="mono text-slate-200">{status?.counts.runs ?? "—"}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-slate-500">Refund receipts</dt>
                      <dd className="mono text-slate-200">{status?.counts.refunds ?? "—"}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-slate-500">Mode</dt>
                      <dd className="mono uppercase text-slate-200">{status?.mode ?? "offline"}</dd>
                    </div>
                  </dl>
                </Panel>
              </div>
            </div>

            <aside className="space-y-5">
              <Panel title="Resolution health" subtitle="disputes by reason">
                <div className="space-y-3">
                  {reasonRows.length === 0 && <p className="text-[11.5px] text-slate-500">No disputes seeded.</p>}
                  {reasonRows.map((row) => (
                    <div key={row.reason_code}>
                      <div className="mb-1 flex items-center justify-between gap-3">
                        <span className="truncate text-[11px] text-slate-300">{reasonLabel(row.reason_code)}</span>
                        <span className="mono text-[10px] text-slate-500">{row.count}</span>
                      </div>
                      <Meter
                        value={row.count}
                        max={Math.max(1, totalReason)}
                        tone={row.resolved > 0 ? "emerald" : "amber"}
                      />
                      <p className="mono mt-1 text-[9px] text-slate-600">
                        at risk {formatMoney(row.at_risk)} · refunded {formatMoney(row.refunded)}
                      </p>
                    </div>
                  ))}
                </div>
              </Panel>

              <Panel title="Execution envelope" subtitle={rules ? `rules v${rules.version}` : "live policy"}>
                <dl className="space-y-2.5 text-[11.5px]">
                  {rules && (
                    <>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-400">Autonomous refund cap</dt>
                        <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.auto_resolve_cap))}</dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-400">Autonomous offer cap</dt>
                        <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.auto_offer_cap))}</dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-400">Hard cap — human</dt>
                        <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.hard_cap))}</dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-400">Auto-approve confidence</dt>
                        <dd className="mono text-slate-200">
                          {Math.round(rules.thresholds.auto_approve_confidence * 100)}%
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-400">Escalate below</dt>
                        <dd className="mono text-slate-200">
                          {Math.round(rules.thresholds.escalate_confidence * 100)}%
                        </dd>
                      </div>
                    </>
                  )}
                </dl>
                <p className="mt-4 border-t border-slate-800 pt-3 text-[10.5px] leading-relaxed text-slate-500">
                  Read live from <span className="mono">rules.yaml</span>. The model never sets these numbers.
                </p>
              </Panel>

              <Panel title="Agent pipeline" subtitle="parallel argument · deterministic gate">
                <ol className="space-y-3">
                  {[
                    ["Buyer", "builds the claim from order + messages"],
                    ["Merchant", "defends with seller-protection facts"],
                    ["Resolution", "adjudicates inside the envelope"],
                    ["Policy gate", "deterministic allow / approve / deny"],
                    ["Payment", "signs the plan; executor pays"],
                  ].map(([name, hint], index) => (
                    <li key={name} className="flex gap-3">
                      <span className="mono mt-0.5 text-[10px] text-slate-600">{String(index + 1).padStart(2, "0")}</span>
                      <div>
                        <p className="text-[11.5px] text-slate-200">{name}</p>
                        <p className="text-[10.5px] leading-relaxed text-slate-500">{hint}</p>
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="mono mt-4 border-t border-slate-800 pt-3 text-[9px] leading-relaxed text-slate-600">
                  max 2 rounds · every LLM step has a labelled deterministic fallback
                </p>
              </Panel>

              <Panel title="What is real here" subtitle="no invented success">
                <ul className="space-y-3 text-[11px] leading-relaxed text-slate-400">
                  <li className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                    Numbers are queried from Postgres on every request — no cached mock state.
                  </li>
                  <li className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                    Agent runs persist typed envelopes, matched rules, tokens and latency.
                  </li>
                  <li className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                    {status?.mode === "replay"
                      ? "Replay mode: refund receipts are simulated and labelled. Live PayPal sandbox is one env flag away."
                      : "Sandbox mode: refunds call the real PayPal API; receipts carry the PayPal refund id."}
                  </li>
                  <li className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                    Every approval decision is appended to a hash-chained audit log.
                  </li>
                </ul>
              </Panel>
            </aside>
          </div>

          <footer className="mono mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/70 pt-4 text-[9px] text-slate-600">
            <span>
              {status?.env} · {status?.mode} mode · {status?.counts.runs ?? 0} runs · {status?.counts.refunds ?? 0} refunds
            </span>
            <span>request {status?.request_id ?? "—"}</span>
          </footer>
        </>
      )}
    </>
  );
}

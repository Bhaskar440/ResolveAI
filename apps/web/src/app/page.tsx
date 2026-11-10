import { DemoControls } from "@/components/DemoControls";
import { DisputeGrid } from "@/components/DisputeGrid";
import { Nav } from "@/components/Nav";
import {
  ApiError,
  getMetrics,
  getPolicyRules,
  getSystemStatus,
  listApprovals,
  type Approval,
  type Metrics,
  type PolicyRules,
  type SystemStatus,
} from "@/lib/api";
import { formatMoney, ReasonBadge, relative } from "@/components/ui";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function Stat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint: string;
  tone?: "good" | "bad" | "warn" | "neutral";
}) {
  const dot = {
    good: "bg-emerald-400",
    bad: "bg-rose-400",
    warn: "bg-amber-400",
    neutral: "bg-slate-500",
  }[tone];
  return (
    <div className="card rounded-xl p-5">
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-slate-400">
          {label}
        </span>
      </div>
      <div className="mt-3 text-[26px] font-semibold leading-none tracking-tight text-slate-100">
        {value}
      </div>
      <div className="mono mt-2 text-[10px] leading-relaxed text-slate-500">{hint}</div>
    </div>
  );
}

function ApprovalRow({ approval }: { approval: Approval }) {
  return (
    <a
      href={`/disputes/${approval.dispute_id}`}
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-900/40 bg-amber-950/10 px-4 py-3 transition hover:border-amber-700/70 hover:bg-amber-950/25"
    >
      <div className="flex items-center gap-3">
        <span className="mono text-[11px] text-amber-200">{approval.case_number ?? approval.dispute_id.slice(0, 8)}</span>
        <ReasonBadge reason={approval.reason_code ?? "UNKNOWN"} short />
        <span className="text-[12px] text-slate-400">
          agent proposes <span className="text-slate-200">{approval.decision_code}</span>
        </span>
      </div>
      <div className="flex items-center gap-4">
        <span className="mono text-[13px] font-medium text-slate-100">
          {formatMoney(approval.amount, approval.currency ?? "USD")}
        </span>
        <span className="mono text-[10px] uppercase tracking-wider text-slate-500">
          expires {relative(approval.expires_at)}
        </span>
        <span className="mono rounded border border-amber-800/70 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-300">
          review →
        </span>
      </div>
    </a>
  );
}

export default async function Home() {
  let status: SystemStatus | null = null;
  let metrics: Metrics | null = null;
  let approvals: Approval[] = [];
  let rules: PolicyRules | null = null;
  let error: string | null = null;

  try {
    [status, metrics, approvals, rules] = await Promise.all([
      getSystemStatus(),
      getMetrics(),
      listApprovals("pending"),
      getPolicyRules(),
    ]);
  } catch (err) {
    error = err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err);
  }

  const live = Boolean(status?.capabilities.live_paypal);

  return (
    <div className="min-h-screen">
      <Nav mode={status?.mode ?? "offline"} live={live} right={<DemoControls />} />

      <main className="mx-auto max-w-7xl px-6 pb-16 pt-8">
        <section className="flex flex-wrap items-end justify-between gap-6 border-b border-slate-800/70 pb-7">
          <div>
            <p className="mono text-[10px] uppercase tracking-[0.22em] text-emerald-400/80">
              PayPal AI Hackathon · agentic commerce
            </p>
            <h1 className="mt-2 max-w-2xl text-[32px] font-semibold leading-[1.12] tracking-tight text-slate-50">
              Autonomous dispute resolution,
              <span className="text-slate-400"> under human control.</span>
            </h1>
            <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-slate-400">
              Buyer and Merchant agents argue the case in parallel. The Resolution agent picks a
              remedy inside a deterministic policy envelope. A signed payment plan is the only path
              to money — and anything outside the envelope waits for you.
            </p>
          </div>
          <div className="mono flex flex-col items-end gap-1 text-[10px] uppercase tracking-wider text-slate-500">
            <span>{status?.app ?? "resolveai"}</span>
            <span>
              {status?.db.connected ? `postgres ${status.db.server_version ?? ""}` : "db unknown"}
            </span>
            <span>{metrics ? `${metrics.median_run_seconds ?? "—"}s median run` : "—"}</span>
          </div>
        </section>

        {error && (
          <section className="mt-6 rounded-xl border border-rose-900/60 bg-rose-950/30 p-5">
            <p className="mono text-[10px] uppercase tracking-wider text-rose-300">api unreachable</p>
            <p className="mt-2 text-sm text-rose-100">
              The dashboard will not invent numbers. Start the stack and refresh.
            </p>
            <pre className="mono mt-3 overflow-x-auto whitespace-pre-wrap text-[11px] leading-relaxed text-rose-300/80">
              {error}
            </pre>
            <p className="mt-3 text-xs text-slate-400">
              <code className="mono rounded bg-slate-900 px-1.5 py-0.5">docker compose up -d</code>{" "}
              then seed with{" "}
              <code className="mono rounded bg-slate-900 px-1.5 py-0.5">
                uv run python -m scripts.seed
              </code>
              .
            </p>
          </section>
        )}

        {metrics && (
          <>
            <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Open disputes"
                value={String(metrics.open_disputes)}
                tone={metrics.open_disputes > 0 ? "warn" : "good"}
                hint={`${metrics.resolved} resolved · ${metrics.escalated} escalated`}
              />
              <Stat
                label="Exposure at risk"
                value={formatMoney(metrics.total_at_risk)}
                tone={Number(metrics.total_at_risk) > 0 ? "warn" : "good"}
                hint="sum of unresolved dispute amounts"
              />
              <Stat
                label="Recovered / refunded"
                value={formatMoney(metrics.recovered)}
                tone="good"
                hint={`${metrics.auto_executed} autonomous · ${metrics.human_executed} human-approved`}
              />
              <Stat
                label="Awaiting approval"
                value={String(metrics.pending_approvals)}
                tone={metrics.pending_approvals > 0 ? "warn" : "good"}
                hint="policy-gated decisions, never auto-executed"
              />
            </section>

            {approvals.length > 0 && (
              <section className="mt-6">
                <div className="mb-2 flex items-center justify-between">
                  <h2 className="text-[13px] font-medium text-slate-200">Needs a human decision</h2>
                  <span className="mono text-[10px] uppercase tracking-wider text-amber-400/80">
                    {approvals.length} pending
                  </span>
                </div>
                <div className="space-y-2">
                  {approvals.map((a) => (
                    <ApprovalRow key={a.id} approval={a} />
                  ))}
                </div>
              </section>
            )}

            <section className="mt-7">
              <div className="mb-3 flex items-end justify-between">
                <div>
                  <h2 className="text-[13px] font-medium text-slate-200">Dispute queue</h2>
                  <p className="mono mt-0.5 text-[10px] text-slate-500">
                    GET /api/v1/disputes · policy-gated outcomes
                  </p>
                </div>
                {status?.mode === "replay" && (
                  <span className="mono rounded border border-slate-800 px-2 py-1 text-[10px] uppercase tracking-wider text-slate-500">
                    replay fixtures — refunds marked simulated
                  </span>
                )}
              </div>
              <div className="card rounded-xl p-4">
                <DisputeGrid />
              </div>
            </section>

            <section className="mt-7 grid gap-4 lg:grid-cols-3">
              <div className="card rounded-xl p-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-[13px] font-medium text-slate-200">Execution envelope</h2>
                  <span className="mono text-[10px] text-slate-500">v{rules?.version ?? "—"}</span>
                </div>
                <dl className="mt-4 space-y-2.5 text-[12px]">
                  {rules && (
                    <>
                      <div className="flex justify-between">
                        <dt className="text-slate-400">Autonomous refund cap</dt>
                        <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.auto_resolve_cap))}</dd>
                      </div>
                      <div className="flex justify-between">
                        <dt className="text-slate-400">Autonomous offer cap</dt>
                        <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.auto_offer_cap))}</dd>
                      </div>
                      <div className="flex justify-between">
                        <dt className="text-slate-400">Hard cap — always human</dt>
                        <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.hard_cap))}</dd>
                      </div>
                      <div className="flex justify-between">
                        <dt className="text-slate-400">Auto-approve confidence</dt>
                        <dd className="mono text-slate-200">
                          {Math.round(rules.thresholds.auto_approve_confidence * 100)}%
                        </dd>
                      </div>
                      <div className="flex justify-between">
                        <dt className="text-slate-400">Escalate below</dt>
                        <dd className="mono text-slate-200">
                          {Math.round(rules.thresholds.escalate_confidence * 100)}%
                        </dd>
                      </div>
                    </>
                  )}
                </dl>
                <p className="mt-4 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
                  Read live from <span className="mono">rules.yaml</span> via the API. The model never
                  sets these numbers.
                </p>
              </div>

              <div className="card rounded-xl p-5">
                <h2 className="text-[13px] font-medium text-slate-200">Agent pipeline</h2>
                <ol className="mt-4 space-y-3">
                  {[
                    ["Buyer", "builds the claim from order + messages"],
                    ["Merchant", "defends with seller-protection facts"],
                    ["Resolution", "adjudicates inside the envelope"],
                    ["Policy gate", "deterministic allow / approve / deny"],
                    ["Payment", "signs the plan; executor pays"],
                  ].map(([name, hint], i) => (
                    <li key={name} className="flex gap-3">
                      <span className="mono mt-0.5 text-[10px] text-slate-600">{String(i + 1).padStart(2, "0")}</span>
                      <div>
                        <p className="text-[12px] text-slate-200">{name}</p>
                        <p className="text-[11px] leading-relaxed text-slate-500">{hint}</p>
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="mono mt-4 border-t border-slate-800 pt-3 text-[10px] leading-relaxed text-slate-500">
                  Buyer + Merchant run in parallel · max 2 rounds · every LLM step has a labelled
                  deterministic fallback
                </p>
              </div>

              <div className="card rounded-xl p-5">
                <h2 className="text-[13px] font-medium text-slate-200">What is real here</h2>
                <ul className="mt-4 space-y-3 text-[12px] leading-relaxed text-slate-400">
                  <li className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                    Numbers are queried from Postgres on every request — no cached mock state.
                  </li>
                  <li className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                    Agent runs persist typed envelopes, policy rules matched, tokens and latency.
                  </li>
                  <li className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                    {status?.mode === "replay"
                      ? "Replay mode: refund receipts are simulated and labelled as such. Live PayPal sandbox is one env flag away."
                      : "Sandbox mode: refunds call the real PayPal API; receipts carry the PayPal refund id."}
                  </li>
                  <li className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                    Every approval decision is appended to a hash-chained audit log.
                  </li>
                </ul>
              </div>
            </section>

            <footer className="mono mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/70 pt-4 text-[10px] text-slate-600">
              <span>
                {status?.env} · {status?.mode} mode · {status?.counts.runs ?? 0} runs ·{" "}
                {status?.counts.refunds ?? 0} refunds
              </span>
              <span>request {status?.request_id ?? "—"}</span>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}

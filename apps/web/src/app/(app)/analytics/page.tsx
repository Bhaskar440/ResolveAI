import Link from "next/link";
import { RefreshButton } from "@/components/RefreshButton";
import {
  getAnalytics,
  getDisputes,
  type Analytics,
  type DisputeList,
} from "@/lib/api";
import {
  formatMoney,
  Meter,
  PageHeader,
  Panel,
  ReasonBadge,
  reasonLabel,
  StatusBadge,
  utc,
} from "@/components/ui";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function TrendChart({ data }: { data: Analytics["trend"] }) {
  const width = 760;
  const height = 210;
  const padX = 32;
  const padY = 24;
  const max = Math.max(1, ...data.map((point) => Math.max(point.created, point.resolved)));
  const x = (index: number) =>
    padX + (index * (width - padX * 2)) / Math.max(1, data.length - 1);
  const y = (value: number) => height - padY - (value / max) * (height - padY * 2);
  const line = (key: "created" | "resolved") =>
    data.map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(point[key]).toFixed(1)}`).join(" ");
  const area = (key: "created" | "resolved") =>
    `${line(key)} L${x(data.length - 1).toFixed(1)},${height - padY} L${x(0).toFixed(1)},${height - padY} Z`;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-4">
        <span className="flex items-center gap-1.5 text-[10px] text-slate-400">
          <span className="h-1.5 w-4 rounded-full bg-emerald-400" /> created
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-slate-400">
          <span className="h-1.5 w-4 rounded-full bg-sky-400" /> resolved
        </span>
        <span className="mono ml-auto text-[9px] uppercase tracking-wider text-slate-600">last 14 days</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[190px] w-full" role="img" aria-label="Dispute trend">
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <line
            key={fraction}
            x1={padX}
            x2={width - padX}
            y1={padY + fraction * (height - padY * 2)}
            y2={padY + fraction * (height - padY * 2)}
            stroke="#1b2536"
            strokeDasharray={fraction === 1 ? undefined : "3 4"}
          />
        ))}
        <path d={area("resolved")} fill="rgba(56,189,248,0.08)" />
        <path d={area("created")} fill="rgba(52,211,153,0.08)" />
        <path d={line("created")} fill="none" stroke="#34d399" strokeWidth="2" />
        <path d={line("resolved")} fill="none" stroke="#38bdf8" strokeWidth="2" />
        {data.map((point, index) =>
          index % 2 === 0 ? (
            <g key={point.date}>
              <circle cx={x(index)} cy={y(point.created)} r="2.5" fill="#34d399" />
              <circle cx={x(index)} cy={y(point.resolved)} r="2.5" fill="#38bdf8" />
              <text x={x(index)} y={height - 6} textAnchor="middle" fill="#64748b" fontSize="9">
                {point.date.slice(5).replace("-", "/")}
              </text>
            </g>
          ) : null,
        )}
      </svg>
    </div>
  );
}

export default async function AnalyticsPage() {
  let analytics: Analytics | null = null;
  let recent: DisputeList | null = null;
  let error: string | null = null;

  try {
    [analytics, recent] = await Promise.all([
      getAnalytics(),
      getDisputes({ limit: 6, sort: "updated_at:desc" }),
    ]);
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  const total = analytics?.total_disputes ?? 0;
  const maxReason = Math.max(1, ...(analytics?.by_reason.map((row) => row.count) ?? [1]));

  return (
    <>
      <PageHeader
        eyebrow="Analytics"
        title="Outcomes, exposure and refunds"
        description="Resolved and pending cases, reason mix and refund totals are aggregated from the live dispute and refund tables. Simulated replay receipts are separated from live PayPal receipts and never counted as live money movement."
        actions={<RefreshButton label="Refresh analytics" />}
      />

      {error && (
        <div className="mb-4 rounded-xl border border-rose-900/60 bg-rose-950/30 p-4">
          <p className="mono text-[10px] uppercase tracking-wider text-rose-300">analytics unavailable</p>
          <p className="mt-1 text-[12px] text-rose-100">{error}</p>
        </div>
      )}

      {analytics && (
        <>
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["Resolved cases", String(analytics.resolved_cases), `${analytics.resolution_rate}% of ${total} disputes`],
              ["Pending cases", String(analytics.pending_cases), `${analytics.awaiting_approval} awaiting approval`],
              ["Refunded total", formatMoney(analytics.refunded_total), `${analytics.refunds.completed} completed receipts`],
              ["Exposure at risk", formatMoney(analytics.total_at_risk), `${analytics.escalated_cases} escalated`],
            ].map(([label, value, hint]) => (
              <div key={label} className="card rounded-xl px-4 py-3.5">
                <p className="mono text-[9px] uppercase tracking-[0.16em] text-slate-500">{label}</p>
                <p className="mt-1.5 text-[23px] font-semibold leading-none tracking-tight text-slate-100">{value}</p>
                <p className="mono mt-1.5 text-[9px] text-slate-600">{hint}</p>
              </div>
            ))}
          </section>

          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(330px,0.8fr)]">
            <Panel
              title="Case flow"
              subtitle="created vs resolved · API aggregate"
              right={
                <span className="mono rounded border border-slate-800 px-2 py-0.5 text-[9px] uppercase tracking-wider text-slate-500">
                  {analytics.median_run_seconds ?? "—"}s median run
                </span>
              }
            >
              <TrendChart data={analytics.trend} />
            </Panel>

            <Panel title="Refund ledger" subtitle="completed vs simulated">
              <dl className="grid grid-cols-2 gap-3">
                {[
                  ["Completed", String(analytics.refunds.completed)],
                  ["Pending", String(analytics.refunds.pending)],
                  ["Failed / denied", String(analytics.refunds.failed)],
                  ["Receipts", String(analytics.refunds.count)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-slate-800/80 bg-slate-900/30 px-3 py-2">
                    <dt className="mono text-[8.5px] uppercase tracking-wider text-slate-500">{label}</dt>
                    <dd className="mono mt-1 text-[17px] text-slate-100">{value}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-3 space-y-2.5 border-t border-slate-800 pt-3">
                <div className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="text-slate-400">Completed amount</span>
                  <span className="mono text-slate-100">{formatMoney(analytics.refunds.amount_completed)}</span>
                </div>
                <div className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="text-slate-400">All receipt amounts</span>
                  <span className="mono text-slate-200">{formatMoney(analytics.refunds.amount_total)}</span>
                </div>
                <div className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="text-amber-400/80">Simulated (replay)</span>
                  <span className="mono text-amber-300">{formatMoney(analytics.refunds.amount_simulated)}</span>
                </div>
                <div className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="text-slate-400">Live PayPal receipts</span>
                  <span className="mono text-emerald-300">{analytics.refunds.live}</span>
                </div>
              </div>
              {analytics.refunds.simulated > 0 && (
                <p className="mono mt-3 rounded border border-amber-900/50 bg-amber-950/20 px-2 py-1.5 text-[9px] leading-relaxed text-amber-300/80">
                  {analytics.refunds.simulated} simulated receipt(s) are labelled in the case file and must not be presented as live PayPal refunds.
                </p>
              )}
            </Panel>
          </div>

          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(330px,0.9fr)]">
            <Panel title="Reason mix" subtitle="count, exposure, resolved and refunded">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[620px] border-collapse text-left">
                  <thead>
                    <tr className="mono border-b border-slate-800 text-[9px] uppercase tracking-wider text-slate-600">
                      <th className="pb-2 font-medium">Reason</th>
                      <th className="pb-2 text-right font-medium">Cases</th>
                      <th className="pb-2 text-right font-medium">At risk</th>
                      <th className="pb-2 text-right font-medium">Resolved</th>
                      <th className="pb-2 text-right font-medium">Refunded</th>
                      <th className="w-[120px] pb-2 pl-4 font-medium">Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analytics.by_reason.map((row) => (
                      <tr key={row.reason_code} className="border-b border-slate-800/60 last:border-0">
                        <td className="py-2.5 pr-3 text-[11px] text-slate-300">{reasonLabel(row.reason_code)}</td>
                        <td className="mono py-2.5 text-right text-[10px] text-slate-300">{row.count}</td>
                        <td className="mono py-2.5 text-right text-[10px] text-slate-400">{formatMoney(row.at_risk)}</td>
                        <td className="mono py-2.5 text-right text-[10px] text-emerald-300">{row.resolved}</td>
                        <td className="mono py-2.5 text-right text-[10px] text-slate-300">{formatMoney(row.refunded)}</td>
                        <td className="py-2.5 pl-4">
                          <Meter value={row.count} max={maxReason} tone={row.resolved > 0 ? "emerald" : "amber"} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Status distribution" subtitle="live dispute states">
              <div className="space-y-3">
                {analytics.by_status.map((row) => (
                  <div key={row.status}>
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="mono text-[9px] uppercase tracking-wider text-slate-400">
                        {row.status.replaceAll("_", " ")}
                      </span>
                      <span className="mono text-[10px] text-slate-300">{row.count}</span>
                    </div>
                    <Meter value={row.count} max={Math.max(1, total)} tone={row.status === "RESOLVED" ? "emerald" : row.status === "ESCALATED" ? "rose" : "amber"} />
                  </div>
                ))}
                {analytics.by_status.length === 0 && <p className="text-[11px] text-slate-500">No disputes yet.</p>}
              </div>
            </Panel>
          </div>

          <Panel title="Recent case activity" subtitle="latest updates" className="mt-5">
            {recent && recent.items.length > 0 ? (
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {recent.items.map((dispute) => (
                  <Link
                    key={dispute.id}
                    href={`/cases/${dispute.id}`}
                    className="rounded-lg border border-slate-800/80 bg-slate-900/30 p-3 transition hover:border-slate-700 hover:bg-slate-800/40"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="mono text-[10px] text-slate-300">
                        {dispute.paypal_case_number ?? dispute.paypal_dispute_id}
                      </span>
                      <span className="mono text-[10px] text-slate-400">
                        {formatMoney(dispute.amount, dispute.currency)}
                      </span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <ReasonBadge reason={dispute.reason_code} short />
                      <StatusBadge status={dispute.status} />
                    </div>
                    <p className="mono mt-1.5 text-[8.5px] text-slate-600">updated {utc(dispute.updated_at)}</p>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-slate-500">No case activity yet.</p>
            )}
          </Panel>
        </>
      )}
    </>
  );
}

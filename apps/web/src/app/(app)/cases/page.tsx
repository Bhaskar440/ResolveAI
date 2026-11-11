import Link from "next/link";
import { CaseExplorer } from "@/components/CaseExplorer";
import { RefreshButton } from "@/components/RefreshButton";
import { formatMoney, PageHeader } from "@/components/ui";
import { getAnalytics, type Analytics } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function CasesPage() {
  let analytics: Analytics | null = null;
  let error: string | null = null;
  try {
    analytics = await getAnalytics();
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  const stats = [
    {
      label: "Total cases",
      value: analytics ? String(analytics.total_disputes) : "—",
      hint: "all disputes in Postgres",
      tone: "text-slate-100",
    },
    {
      label: "Pending",
      value: analytics ? String(analytics.pending_cases) : "—",
      hint: "open or waiting on a human",
      tone: "text-amber-300",
    },
    {
      label: "Resolved",
      value: analytics ? String(analytics.resolved_cases) : "—",
      hint: analytics ? `${analytics.resolution_rate}% resolution rate` : "resolved cases",
      tone: "text-emerald-300",
    },
    {
      label: "At risk",
      value: analytics ? formatMoney(analytics.total_at_risk) : "—",
      hint: "unresolved exposure",
      tone: "text-slate-100",
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Case management"
        title="Every dispute, one queue"
        description="Search, filter and sort the live dispute book. Pagination and sorting are handled by the API, not by the browser. Click any row to inspect the complaint, agent transcript, policy citations and payment status."
        actions={
          <>
            <RefreshButton label="Refresh queue" />
            <Link
              href="/complaints"
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-[11px] font-medium text-slate-200 transition hover:border-slate-500 hover:bg-slate-800"
            >
              Complaint inbox →
            </Link>
          </>
        }
      />

      {error && (
        <div className="mb-4 rounded-xl border border-rose-900/60 bg-rose-950/30 p-4">
          <p className="mono text-[10px] uppercase tracking-wider text-rose-300">queue unavailable</p>
          <p className="mt-1 text-[12px] text-rose-100">{error}</p>
        </div>
      )}

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="card rounded-xl px-4 py-3.5">
            <p className="mono text-[9px] uppercase tracking-[0.16em] text-slate-500">{stat.label}</p>
            <p className={`mt-1.5 text-[22px] font-semibold leading-none tracking-tight ${stat.tone}`}>
              {stat.value}
            </p>
            <p className="mono mt-1.5 text-[9px] text-slate-600">{stat.hint}</p>
          </div>
        ))}
      </div>

      <CaseExplorer />
    </>
  );
}

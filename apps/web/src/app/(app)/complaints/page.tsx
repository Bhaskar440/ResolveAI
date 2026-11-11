import { ComplaintWorkspace } from "@/components/ComplaintWorkspace";
import { RefreshButton } from "@/components/RefreshButton";
import { getAnalytics, getComplaints, type Analytics, type ComplaintList } from "@/lib/api";
import { PageHeader } from "@/components/ui";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function ComplaintsPage() {
  let complaints: ComplaintList | null = null;
  let analytics: Analytics | null = null;
  let error: string | null = null;

  try {
    [complaints, analytics] = await Promise.all([getComplaints({ limit: 100 }), getAnalytics()]);
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  const withMessages = complaints?.items.filter((item) => item.message_count > 0).length ?? 0;
  const needsReply = complaints?.items.filter((item) => item.status === "AWAITING_INFO").length ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="Customer complaint interface"
        title="Complaint workspace"
        description="Read the buyer's actual PayPal complaint, inspect the case file and add a merchant note that persists to PostgreSQL. The note is available to the next agent run; outbound PayPal messaging is not claimed in this build."
        actions={<RefreshButton label="Refresh complaints" />}
      />

      {error && (
        <div className="mb-4 rounded-xl border border-rose-900/60 bg-rose-950/30 p-4">
          <p className="mono text-[10px] uppercase tracking-wider text-rose-300">complaints unavailable</p>
          <p className="mt-1 text-[12px] text-rose-100">{error}</p>
        </div>
      )}

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          ["Complaints", complaints?.total ?? "—", "disputes with a complaint file"],
          ["With buyer messages", withMessages, "message threads from ingestion"],
          ["Needs information", needsReply, "awaiting buyer evidence"],
          [
            "Resolved",
            analytics?.resolved_cases ?? "—",
            analytics ? `${analytics.resolution_rate}% resolution rate` : "resolved cases",
          ],
        ].map(([label, value, hint]) => (
          <div key={String(label)} className="card rounded-xl px-4 py-3.5">
            <p className="mono text-[9px] uppercase tracking-[0.16em] text-slate-500">{label}</p>
            <p className="mt-1.5 text-[22px] font-semibold leading-none text-slate-100">{value}</p>
            <p className="mono mt-1.5 text-[9px] text-slate-600">{hint}</p>
          </div>
        ))}
      </div>

      <ComplaintWorkspace initialItems={complaints?.items ?? []} />
    </>
  );
}

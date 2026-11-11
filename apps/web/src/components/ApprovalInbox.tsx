"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { decideApproval, type Approval } from "@/lib/api";
import { formatMoney, ReasonBadge, relative } from "./ui";

export function ApprovalInbox({ approvals }: { approvals: Approval[] }) {
  const router = useRouter();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (approvals.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/20 px-4 py-8 text-center">
        <p className="text-[12px] text-slate-400">No decisions are waiting on a human.</p>
        <p className="mono mt-1 text-[9px] uppercase tracking-wider text-slate-600">
          policy-gated work stays inside the envelope
        </p>
      </div>
    );
  }

  async function decide(approval: Approval, approve: boolean) {
    if (
      !window.confirm(
        approve
          ? `Approve ${approval.decision_code ?? "this remedy"} for ${formatMoney(approval.amount, approval.currency ?? "USD")}? This executes the signed payment plan exactly once.`
          : "Reject this recommendation? The case will not move money.",
      )
    ) {
      return;
    }
    setBusy(approval.id);
    setError(null);
    try {
      await decideApproval(approval.id, approve, notes[approval.id]?.trim() || undefined);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2.5">
      {error && (
        <div className="mono rounded border border-rose-900/60 bg-rose-950/30 px-3 py-2 text-[10px] text-rose-300">
          {error}
        </div>
      )}
      {approvals.map((approval) => (
        <div
          key={approval.id}
          className="rounded-lg border border-amber-900/40 bg-amber-950/10 p-3 transition hover:border-amber-800/70"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  href={`/cases/${approval.dispute_id}`}
                  className="mono text-[11px] text-amber-200 hover:underline"
                >
                  {approval.case_number ?? approval.dispute_id.slice(0, 8)}
                </Link>
                <ReasonBadge reason={approval.reason_code ?? "UNKNOWN"} short />
                <span className="mono rounded border border-amber-900/70 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-amber-300">
                  {approval.decision_code ?? "review"}
                </span>
              </div>
              <p className="mt-1.5 line-clamp-2 max-w-2xl text-[11.5px] leading-relaxed text-slate-400">
                {approval.rationale ?? "Policy requires a human before money moves."}
              </p>
              <p className="mono mt-1 text-[9px] text-slate-600">
                expires {relative(approval.expires_at)} · confidence{" "}
                {approval.confidence ? `${Math.round(Number(approval.confidence) * 100)}%` : "—"}
              </p>
            </div>
            <span className="mono text-[14px] font-medium text-slate-100">
              {formatMoney(approval.amount, approval.currency ?? "USD")}
            </span>
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <input
              value={notes[approval.id] ?? ""}
              onChange={(event) =>
                setNotes((current) => ({ ...current, [approval.id]: event.target.value }))
              }
              placeholder="Optional audit note"
              className="mono min-w-[160px] flex-1 rounded border border-slate-800 bg-[#0a1019] px-2 py-1.5 text-[10px] text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
            />
            <button
              onClick={() => decide(approval, true)}
              disabled={busy !== null}
              className="mono rounded border border-emerald-700 bg-emerald-900/50 px-2.5 py-1.5 text-[9px] uppercase tracking-wider text-emerald-200 hover:bg-emerald-800/60 disabled:opacity-40"
            >
              {busy === approval.id ? "working…" : "approve & pay"}
            </button>
            <button
              onClick={() => decide(approval, false)}
              disabled={busy !== null}
              className="mono rounded border border-rose-900 bg-rose-950/40 px-2.5 py-1.5 text-[9px] uppercase tracking-wider text-rose-300 hover:bg-rose-900/40 disabled:opacity-40"
            >
              reject
            </button>
            <Link
              href={`/cases/${approval.dispute_id}`}
              className="mono rounded border border-slate-800 px-2.5 py-1.5 text-[9px] uppercase tracking-wider text-slate-500 hover:border-slate-600 hover:text-slate-300"
            >
              inspect
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}

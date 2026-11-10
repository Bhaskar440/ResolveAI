"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { decideApproval, runDispute } from "@/lib/api";

export function DisputeActions({
  disputeId,
  canRun,
  approvalId,
}: {
  disputeId: string;
  canRun: boolean;
  approvalId: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<"run" | "approve" | "reject" | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  async function run() {
    setBusy("run");
    setError(null);
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    try {
      await runDispute(disputeId);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      window.clearInterval(timer);
      setBusy(null);
    }
  }

  async function decide(approve: boolean) {
    if (!approvalId) return;
    setBusy(approve ? "approve" : "reject");
    setError(null);
    try {
      await decideApproval(approvalId, approve, note.trim() || undefined);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      {canRun && (
        <button
          onClick={run}
          disabled={busy !== null}
          className="mono inline-flex w-full items-center justify-center gap-2 rounded-md border border-emerald-700/70 bg-emerald-950/40 px-3 py-2 text-[11px] uppercase tracking-wider text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-50"
        >
          {busy === "run" ? `running agents… ${elapsed}s` : "Run agents"}
        </button>
      )}

      {approvalId && (
        <div className="space-y-2 rounded-md border border-amber-900/60 bg-amber-950/20 p-3">
          <p className="text-[11px] leading-relaxed text-amber-200/90">
            Policy requires a human before money moves. Approving executes the signed payment plan
            exactly once.
          </p>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional note for the audit log"
            className="mono w-full rounded border border-slate-800 bg-[#0a1019] px-2 py-1.5 text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              onClick={() => decide(true)}
              disabled={busy !== null}
              className="mono flex-1 rounded border border-emerald-700 bg-emerald-900/50 px-2 py-1.5 text-[10px] uppercase tracking-wider text-emerald-200 hover:bg-emerald-800/60 disabled:opacity-50"
            >
              {busy === "approve" ? "executing…" : "Approve & pay"}
            </button>
            <button
              onClick={() => decide(false)}
              disabled={busy !== null}
              className="mono flex-1 rounded border border-rose-900 bg-rose-950/40 px-2 py-1.5 text-[10px] uppercase tracking-wider text-rose-300 hover:bg-rose-900/40 disabled:opacity-50"
            >
              {busy === "reject" ? "rejecting…" : "Reject"}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="mono rounded border border-rose-900/60 bg-rose-950/30 px-2 py-1.5 text-[10px] leading-relaxed text-rose-300">
          {error}
        </div>
      )}
    </div>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  getComplaints,
  getDispute,
  type Complaint,
  type DisputeDetail,
} from "@/lib/api";
import { ComplaintThread } from "./ComplaintThread";
import { formatMoney, ReasonBadge, relative, StatusBadge, utc } from "./ui";

const STATUS_FILTERS = [
  { label: "All complaints", value: "" },
  { label: "Open", value: "RECEIVED,ANALYZING,AWAITING_INFO,AWAITING_APPROVAL,REFUND_PENDING" },
  { label: "Awaiting approval", value: "AWAITING_APPROVAL" },
  { label: "Resolved", value: "RESOLVED" },
  { label: "Escalated", value: "ESCALATED" },
];

export function ComplaintWorkspace({ initialItems }: { initialItems: Complaint[] }) {
  const [items, setItems] = useState(initialItems);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(
    initialItems.length > 0 ? initialItems[0].dispute_id : null,
  );
  const [detail, setDetail] = useState<DisputeDetail | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstLoad = useRef(true);
  const selectedRef = useRef<string | null>(selectedId);

  const selected = useMemo(
    () => items.find((item) => item.dispute_id === selectedId) ?? null,
    [items, selectedId],
  );

  useEffect(() => {
    selectedRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    if (firstLoad.current) {
      firstLoad.current = false;
      return;
    }
    const timer = window.setTimeout(async () => {
      setLoadingList(true);
      try {
        const result = await getComplaints({
          q: query.trim() || undefined,
          status: status || undefined,
          limit: 100,
        });
        setItems(result.items);
        setError(null);
        if (result.items.length > 0 && !result.items.some((item) => item.dispute_id === selectedRef.current)) {
          setSelectedId(result.items[0].dispute_id);
        }
        if (result.items.length === 0) {
          setSelectedId(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoadingList(false);
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, status]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    setError(null);
    getDispute(selectedId)
      .then((result) => {
        if (!cancelled) setDetail(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  return (
    <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
      <section className="card flex min-h-[560px] flex-col rounded-xl">
        <div className="border-b border-slate-800/70 p-3">
          <div className="relative">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search buyer, case or narrative…"
              className="mono w-full rounded-md border border-slate-800 bg-[#0a1019] px-3 py-2 text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
            />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="mono flex-1 rounded-md border border-slate-800 bg-[#0a1019] px-2.5 py-1.5 text-[10px] text-slate-300 outline-none focus:border-slate-600"
            >
              {STATUS_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="mono text-[9px] uppercase tracking-wider text-slate-600">
              {loadingList ? "loading…" : `${items.length} shown`}
            </span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2" style={{ maxHeight: 680 }}>
          {items.length === 0 && !loadingList && (
            <div className="px-4 py-12 text-center">
              <p className="text-[12px] text-slate-400">No complaints match.</p>
              <p className="mono mt-1 text-[9px] text-slate-600">Buyer messages come from PayPal dispute ingestion.</p>
            </div>
          )}
          <div className="space-y-1.5">
            {items.map((item) => {
              const active = item.dispute_id === selectedId;
              return (
                <button
                  key={item.dispute_id}
                  onClick={() => setSelectedId(item.dispute_id)}
                  className={`w-full rounded-lg border px-3 py-2.5 text-left transition ${
                    active
                      ? "border-emerald-500/30 bg-emerald-500/10"
                      : "border-transparent hover:border-slate-800 hover:bg-slate-800/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="mono text-[10px] text-slate-300">
                      {item.paypal_case_number ?? item.paypal_dispute_id}
                    </span>
                    <span className="mono text-[10px] text-slate-400">
                      {formatMoney(item.amount, item.currency)}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <ReasonBadge reason={item.reason_code} short />
                    <StatusBadge status={item.status} />
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[10.5px] leading-relaxed text-slate-500">
                    {item.last_message ?? item.reason_detail ?? "No message recorded."}
                  </p>
                  <div className="mono mt-1.5 flex items-center justify-between text-[8.5px] text-slate-600">
                    <span>
                      {item.buyer_label ?? "buyer"} · {item.message_count} message{item.message_count === 1 ? "" : "s"}
                    </span>
                    <span>{relative(item.response_due_by)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <section className="card min-h-[560px] rounded-xl">
        {!selectedId ? (
          <div className="grid h-full min-h-[520px] place-items-center px-6 text-center">
            <div>
              <p className="text-[13px] text-slate-300">Select a complaint</p>
              <p className="mt-1 text-[11px] text-slate-500">Choose a case from the inbox to read the buyer thread.</p>
            </div>
          </div>
        ) : (
          <div>
            <div className="border-b border-slate-800/70 p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="mono text-[16px] font-semibold text-slate-100">
                      {selected?.paypal_case_number ?? selectedId.slice(0, 8)}
                    </h2>
                    {selected && <ReasonBadge reason={selected.reason_code} />}
                    {selected && <StatusBadge status={selected.status} />}
                  </div>
                  <p className="mono mt-1.5 text-[9px] text-slate-600">
                    buyer {selected?.buyer_label ?? "—"} · due {utc(selected?.response_due_by)} ·{" "}
                    {selected?.message_count ?? 0} message(s)
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="mono text-[15px] text-slate-100">
                    {formatMoney(selected?.amount, selected?.currency)}
                  </span>
                  <Link
                    href={`/cases/${selectedId}`}
                    className="mono rounded border border-slate-800 px-2.5 py-1.5 text-[9px] uppercase tracking-wider text-slate-500 hover:border-slate-600 hover:text-slate-300"
                  >
                    full case →
                  </Link>
                </div>
              </div>
              <p className="mt-3 max-w-3xl text-[12px] leading-relaxed text-slate-400">
                {selected?.reason_detail ?? "No buyer narrative recorded."}
              </p>
            </div>

            <div className="p-4 sm:p-5">
              {error && (
                <div className="mb-3 rounded border border-rose-900/60 bg-rose-950/30 px-3 py-2 text-[11px] text-rose-300">
                  {error}
                </div>
              )}
              {loadingDetail && !detail ? (
                <p className="mono py-10 text-center text-[10px] uppercase tracking-wider text-slate-600">
                  loading complaint thread…
                </p>
              ) : detail ? (
                <ComplaintThread disputeId={detail.dispute.id} messages={detail.messages} compact />
              ) : null}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

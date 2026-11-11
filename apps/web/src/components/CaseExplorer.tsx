"use client";

import { useMemo, useState } from "react";
import { DisputeGrid } from "./DisputeGrid";
import { reasonLabel } from "./ui";

const STATUS_FILTERS = [
  { label: "All statuses", value: "" },
  { label: "Open", value: "RECEIVED,ANALYZING,AWAITING_INFO,AWAITING_APPROVAL,REFUND_PENDING" },
  { label: "Awaiting approval", value: "AWAITING_APPROVAL" },
  { label: "Resolved", value: "RESOLVED" },
  { label: "Escalated", value: "ESCALATED" },
  { label: "Awaiting info", value: "AWAITING_INFO" },
];

const REASONS = [
  "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
  "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
  "UNAUTHORISED",
  "DUPLICATE_TRANSACTION",
  "CREDIT_NOT_PROCESSED",
  "INCORRECT_AMOUNT",
];

const SORTS = [
  { label: "Due soonest", value: "response_due_by:asc" },
  { label: "Highest amount", value: "amount:desc" },
  { label: "Newest first", value: "created_at:desc" },
  { label: "Lowest confidence", value: "confidence:asc" },
  { label: "Status", value: "status:asc" },
];

const selectClass =
  "mono rounded-md border border-slate-800 bg-[#0a1019] px-2.5 py-2 text-[10px] text-slate-300 outline-none focus:border-slate-600";

export function CaseExplorer() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [reason, setReason] = useState("");
  const [sort, setSort] = useState("response_due_by:asc");

  const activeCount = useMemo(
    () => [query.trim(), status, reason].filter(Boolean).length,
    [query, status, reason],
  );

  return (
    <div className="space-y-4">
      <div className="card rounded-xl p-3 sm:p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search case number, buyer, reason or narrative…"
              className="mono w-full rounded-md border border-slate-800 bg-[#0a1019] px-3 py-2 text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
            />
            {query && (
              <button
                onClick={() => setQuery("")}
                className="mono absolute right-2 top-1/2 -translate-y-1/2 text-[9px] uppercase text-slate-600 hover:text-slate-300"
              >
                clear
              </button>
            )}
          </div>

          <select value={status} onChange={(event) => setStatus(event.target.value)} className={selectClass}>
            {STATUS_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <select value={reason} onChange={(event) => setReason(event.target.value)} className={selectClass}>
            <option value="">All reasons</option>
            {REASONS.map((value) => (
              <option key={value} value={value}>
                {reasonLabel(value)}
              </option>
            ))}
          </select>

          <select value={sort} onChange={(event) => setSort(event.target.value)} className={selectClass}>
            {SORTS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          {activeCount > 0 && (
            <button
              onClick={() => {
                setQuery("");
                setStatus("");
                setReason("");
              }}
              className="mono rounded-md border border-slate-800 px-2.5 py-2 text-[9px] uppercase tracking-wider text-slate-500 hover:border-slate-600 hover:text-slate-300"
            >
              reset {activeCount} filter{activeCount === 1 ? "" : "s"}
            </button>
          )}
        </div>
        <div className="mono mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[9px] uppercase tracking-wider text-slate-600">
          <span>AG Grid Community</span>
          <span>·</span>
          <span>server-side pagination</span>
          <span>·</span>
          <span>click a row for the case file</span>
        </div>
      </div>

      <div className="card rounded-xl p-3 sm:p-4">
        <DisputeGrid
          status={status || undefined}
          reason={reason || undefined}
          sort={sort}
          searchQuery={query}
          showToolbar={false}
          heightClass="h-[540px] sm:h-[640px]"
          emptyMessage="No cases match these filters."
        />
      </div>
    </div>
  );
}

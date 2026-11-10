"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
  type IDatasource,
  type RowClickedEvent,
} from "ag-grid-community";
import { getDisputes, type Dispute } from "@/lib/api";
import { ConfidenceBar, formatMoney, ReasonBadge, StatusBadge, utc } from "./ui";

ModuleRegistry.registerModules([AllCommunityModule]);

const theme = themeQuartz.withParams({
  backgroundColor: "#0b111b",
  foregroundColor: "#dbe5f1",
  headerBackgroundColor: "#0a1019",
  headerTextColor: "#8fa3bb",
  borderColor: "#1b2536",
  rowHoverColor: "#111a28",
  oddRowBackgroundColor: "#0c1420",
  accentColor: "#34d399",
  fontSize: 12,
  headerFontSize: 10,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
});

const SORTABLE = new Set(["response_due_by", "amount", "confidence", "status", "created_at"]);

export function DisputeGrid() {
  const router = useRouter();
  const gridRef = useRef<AgGridReact<Dispute>>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<number | null>(null);

  const datasource = useMemo<IDatasource>(
    () => ({
      getRows: async (params) => {
        try {
          const limit = Math.max(1, params.endRow - params.startRow);
          const sortModel = params.sortModel?.[0];
          const sort =
            sortModel && SORTABLE.has(sortModel.colId)
              ? `${sortModel.colId}:${sortModel.sort ?? "asc"}`
              : "response_due_by:asc";
          const res = await getDisputes({
            limit,
            offset: params.startRow,
            sort,
            q: query.trim() || undefined,
          });
          setError(null);
          setLoaded(res.total);
          params.successCallback(res.items, res.total);
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
          params.failCallback();
        }
      },
    }),
    [query],
  );

  useEffect(() => {
    gridRef.current?.api?.purgeInfiniteCache();
  }, [query]);

  const columnDefs = useMemo<ColDef<Dispute>[]>(
    () => [
      {
        headerName: "Case",
        colId: "paypal_case_number",
        width: 138,
        pinned: "left",
        cellRenderer: (p: ICellRendererParams<Dispute>) => (
          <span className="mono text-[12px] text-slate-200">{p.data?.paypal_case_number ?? "—"}</span>
        ),
      },
      {
        headerName: "Reason",
        colId: "reason_code",
        width: 168,
        cellRenderer: (p: ICellRendererParams<Dispute>) => (
          <ReasonBadge reason={p.data?.reason_code ?? "UNKNOWN"} short />
        ),
      },
      {
        headerName: "Buyer",
        field: "buyer_label",
        width: 122,
        cellClass: "text-slate-400",
      },
      {
        headerName: "Amount",
        colId: "amount",
        width: 112,
        type: "rightAligned",
        cellRenderer: (p: ICellRendererParams<Dispute>) => (
          <span className="mono text-[12px] text-slate-100">
            {formatMoney(p.data?.amount, p.data?.currency)}
          </span>
        ),
      },
      {
        headerName: "Status",
        colId: "status",
        width: 158,
        cellRenderer: (p: ICellRendererParams<Dispute>) => <StatusBadge status={p.data?.status ?? ""} />,
      },
      {
        headerName: "Confidence",
        colId: "confidence",
        width: 132,
        cellRenderer: (p: ICellRendererParams<Dispute>) => (
          <ConfidenceBar value={p.data?.confidence ?? null} />
        ),
      },
      {
        headerName: "Decision",
        field: "decision_code",
        width: 150,
        cellRenderer: (p: ICellRendererParams<Dispute>) => (
          <span className="mono text-[11px] text-slate-400">{p.data?.decision_code ?? "not run"}</span>
        ),
      },
      {
        headerName: "Due",
        colId: "response_due_by",
        width: 168,
        cellRenderer: (p: ICellRendererParams<Dispute>) => (
          <span className="mono text-[11px] text-slate-400">{utc(p.data?.response_due_by)}</span>
        ),
      },
      {
        headerName: "Approval",
        colId: "requires_approval",
        width: 104,
        sortable: false,
        cellRenderer: (p: ICellRendererParams<Dispute>) =>
          p.data?.requires_approval ? (
            <span className="mono text-[10px] uppercase tracking-wider text-amber-300">human</span>
          ) : (
            <span className="mono text-[10px] uppercase tracking-wider text-slate-600">auto</span>
          ),
      },
    ],
    [],
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="relative">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search case, buyer or reason…"
            className="mono w-72 rounded-md border border-slate-800 bg-[#0a1019] px-3 py-1.5 text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
          />
        </div>
        <div className="mono flex items-center gap-3 text-[10px] uppercase tracking-wider text-slate-500">
          <span>{loaded === null ? "loading…" : `${loaded} disputes`}</span>
          <span className="text-slate-700">·</span>
          <span>infinite row model</span>
          <span className="text-slate-700">·</span>
          <span>server pagination 25/page</span>
        </div>
      </div>

      {error && (
        <div className="mono mb-3 rounded border border-rose-900/60 bg-rose-950/30 px-3 py-2 text-[11px] text-rose-300">
          {error}
        </div>
      )}

      <div className="h-[520px] overflow-hidden rounded-lg border border-slate-800">
        <AgGridReact<Dispute>
          ref={gridRef}
          theme={theme}
          rowModelType="infinite"
          cacheBlockSize={25}
          maxConcurrentDatasourceRequests={1}
          datasource={datasource}
          columnDefs={columnDefs}
          defaultColDef={{ sortable: true, resizable: true, suppressHeaderMenuButton: true }}
          rowHeight={44}
          headerHeight={38}
          animateRows
          getRowId={(p) => p.data.id}
          onRowClicked={(e: RowClickedEvent<Dispute>) => {
            if (e.data) router.push(`/disputes/${e.data.id}`);
          }}
          overlayNoRowsTemplate='<span style="color:#64748b;font-size:12px">No disputes match. Seed the demo data.</span>'
        />
      </div>
      <p className="mono mt-2 text-[10px] text-slate-600">
        Click a row for the full case file, agent transcript and policy envelope.
      </p>
    </div>
  );
}

export function formatMoney(amount: string | null | undefined, currency = "USD") {
  if (amount === null || amount === undefined) return "—";
  const value = Number(amount);
  if (Number.isNaN(value)) return `${amount} ${currency}`;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(value);
}

export function utc(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

export function relative(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return "—";
  const diff = d - Date.now();
  const abs = Math.abs(diff);
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [86400000, "day"],
    [3600000, "hour"],
    [60000, "minute"],
  ];
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [ms, unit] of units) {
    if (abs >= ms) return fmt.format(Math.round(diff / ms), unit);
  }
  return "now";
}

const STATUS_STYLES: Record<string, string> = {
  RECEIVED: "border-slate-700 bg-slate-900 text-slate-300",
  ANALYZING: "border-sky-800 bg-sky-950/60 text-sky-300",
  AWAITING_INFO: "border-violet-800 bg-violet-950/60 text-violet-300",
  AWAITING_APPROVAL: "border-amber-800 bg-amber-950/60 text-amber-300",
  RESOLVED: "border-emerald-800 bg-emerald-950/60 text-emerald-300",
  ESCALATED: "border-rose-800 bg-rose-950/60 text-rose-300",
  REFUND_PENDING: "border-amber-800 bg-amber-950/60 text-amber-300",
  FAILED: "border-rose-800 bg-rose-950/60 text-rose-300",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] ?? STATUS_STYLES.RECEIVED;
  return (
    <span className={`mono inline-flex rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${cls}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

const REASON_LABEL: Record<string, string> = {
  MERCHANDISE_OR_SERVICE_NOT_RECEIVED: "Item not received",
  MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED: "Not as described",
  UNAUTHORISED: "Unauthorised",
  DUPLICATE_TRANSACTION: "Duplicate",
  CREDIT_NOT_PROCESSED: "Credit not processed",
  INCORRECT_AMOUNT: "Incorrect amount",
};

const REASON_STYLE: Record<string, string> = {
  MERCHANDISE_OR_SERVICE_NOT_RECEIVED: "border-sky-900 bg-sky-950/40 text-sky-300",
  MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED: "border-violet-900 bg-violet-950/40 text-violet-300",
  UNAUTHORISED: "border-rose-900 bg-rose-950/40 text-rose-300",
};

export function ReasonBadge({ reason, short = false }: { reason: string; short?: boolean }) {
  const label = short
    ? reason.includes("NOT_RECEIVED")
      ? "INR"
      : reason.includes("NOT_AS_DESCRIBED")
        ? "SNAD"
        : reason.replaceAll("_", " ")
    : (REASON_LABEL[reason] ?? reason.replaceAll("_", " "));
  const cls = REASON_STYLE[reason] ?? "border-slate-700 bg-slate-900 text-slate-300";
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {label}
    </span>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`card rounded-xl ${className}`}>{children}</div>;
}

export function ConfidenceBar({ value }: { value: string | null }) {
  if (value === null || value === undefined) return <span className="mono text-[11px] text-slate-600">—</span>;
  const pct = Math.round(Number(value) * 100);
  const tone = pct >= 80 ? "bg-emerald-400" : pct >= 55 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-14 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full ${tone}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <span className="mono text-[11px] text-slate-400">{pct}%</span>
    </div>
  );
}

export function AgentDot({ agent }: { agent: string }) {
  const tone: Record<string, string> = {
    buyer: "bg-sky-400",
    merchant: "bg-violet-400",
    resolution: "bg-emerald-400",
    payment: "bg-amber-400",
    system: "bg-slate-500",
  };
  return <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${tone[agent] ?? "bg-slate-500"}`} />;
}

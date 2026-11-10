import { RefreshButton } from "@/components/RefreshButton";
import { getDisputes, getSystemStatus } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const utc = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().replace("T", " ").slice(0, 19)} UTC`;
};

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
        <span className="text-[11px] font-medium uppercase tracking-widest text-slate-400">
          {label}
        </span>
      </div>
      <div className="mt-3 text-2xl font-semibold tracking-tight text-slate-100">{value}</div>
      <div className="mono mt-2 text-[11px] leading-relaxed text-slate-500">{hint}</div>
    </div>
  );
}

function Badge({ children, tone }: { children: React.ReactNode; tone: "good" | "warn" | "bad" }) {
  const cls = {
    good: "border-emerald-800 bg-emerald-950/60 text-emerald-300",
    warn: "border-amber-800 bg-amber-950/50 text-amber-300",
    bad: "border-rose-800 bg-rose-950/50 text-rose-300",
  }[tone];
  return (
    <span className={`mono rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${cls}`}>
      {children}
    </span>
  );
}

export default async function Home() {
  const [status, disputes] = await Promise.all([getSystemStatus(), getDisputes()]);

  const apiUp = status.ok;
  const dbUp = status.ok && status.data.db.connected;

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-2 text-slate-400">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
              <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity=".4" />
              <path d="M5 8.4l2 1.9 4-4.6" stroke="#34d399" strokeWidth="1.4" />
            </svg>
            <span className="mono text-[11px] uppercase tracking-[0.2em]">ResolveAI</span>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            Dispute control tower
          </h1>
          <p className="mt-1 max-w-xl text-sm text-slate-400">
            Live stack check. Every number below is read from the API and the database on this
            request — nothing is cached, mocked or hardcoded.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {apiUp ? (
            <Badge tone="good">{status.data.mode} mode</Badge>
          ) : (
            <Badge tone="bad">api unreachable</Badge>
          )}
          <RefreshButton />
        </div>
      </header>

      {!apiUp && (
        <section className="mt-6 rounded-xl border border-rose-900/60 bg-rose-950/30 p-5">
          <div className="flex items-center gap-2">
            <Badge tone="bad">connection failed</Badge>
            <span className="text-sm font-medium text-rose-200">
              The frontend is up, but it cannot reach the API.
            </span>
          </div>
          <pre className="mono mt-3 overflow-x-auto whitespace-pre-wrap text-[11px] leading-relaxed text-rose-300/90">
            {status.error}
          </pre>
          <p className="mt-3 text-xs text-slate-400">
            Start the backend with{" "}
            <code className="mono rounded bg-slate-900 px-1.5 py-0.5 text-slate-300">
              docker compose up -d db api
            </code>{" "}
            or{" "}
            <code className="mono rounded bg-slate-900 px-1.5 py-0.5 text-slate-300">
              cd apps/api &amp;&amp; uv run uvicorn app.main:app --port 8000
            </code>
            .
          </p>
        </section>
      )}

      {apiUp && (
        <>
          <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="API"
              value="reachable"
              tone="good"
              hint={`request ${status.data.request_id}`}
            />
            <Stat
              label="Postgres"
              value={status.data.db.connected ? "connected" : "down"}
              tone={status.data.db.connected ? "good" : "bad"}
              hint={
                status.data.db.connected
                  ? `${status.data.db.latency_ms} ms · ${status.data.schema_tables} tables`
                  : status.data.db.error ?? "no details"
              }
            />
            <Stat
              label="Disputes"
              value={String(status.data.counts.disputes)}
              tone={status.data.counts.disputes === 0 ? "warn" : "good"}
              hint={`${status.data.counts.runs} runs · ${status.data.counts.refunds} refunds`}
            />
            <Stat
              label="Verified at"
              value={utc(status.data.checked_at).slice(11, 19)}
              hint={`${status.data.env} environment`}
            />
          </section>

          <section className="mt-4 grid gap-4 lg:grid-cols-3">
            <div className="card rounded-xl p-5 lg:col-span-2">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium text-slate-200">Disputes</h2>
                <span className="mono text-[11px] text-slate-500">
                  GET /api/v1/disputes
                </span>
              </div>
              {!disputes.ok ? (
                <p className="mono mt-4 rounded border border-rose-900/60 bg-rose-950/30 p-3 text-[11px] text-rose-300">
                  {disputes.error}
                </p>
              ) : disputes.data.items.length === 0 ? (
                <div className="mt-8 mb-6 text-center">
                  <p className="text-sm text-slate-300">No disputes ingested yet.</p>
                  <p className="mx-auto mt-2 max-w-sm text-xs leading-relaxed text-slate-500">
                    The table is empty because the database is empty — this is the real state, not a
                    placeholder. Ingestion arrives with the PayPal adapter milestone.
                  </p>
                </div>
              ) : (
                <table className="mt-4 w-full text-left text-xs">
                  <thead className="text-slate-500">
                    <tr>
                      <th className="pb-2 font-medium">Case</th>
                      <th className="pb-2 font-medium">Reason</th>
                      <th className="pb-2 font-medium">Amount</th>
                      <th className="pb-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {disputes.data.items.map((d) => (
                      <tr key={d.id}>
                        <td className="mono py-2 text-slate-300">
                          {d.paypal_case_number ?? d.id.slice(0, 8)}
                        </td>
                        <td className="py-2 text-slate-400">{d.reason_code}</td>
                        <td className="mono py-2 text-slate-200">
                          {d.amount} {d.currency}
                        </td>
                        <td className="py-2 text-slate-400">{d.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="card rounded-xl p-5">
              <h2 className="text-sm font-medium text-slate-200">Capabilities</h2>
              <ul className="mt-4 space-y-3 text-xs">
                <li className="flex items-center justify-between">
                  <span className="text-slate-400">PayPal sandbox credentials</span>
                  <Badge tone={status.data.capabilities.paypal_credentials ? "good" : "warn"}>
                    {status.data.capabilities.paypal_credentials ? "verified" : "not configured"}
                  </Badge>
                </li>
                <li className="flex items-center justify-between">
                  <span className="text-slate-400">LLM provider</span>
                  <Badge tone={status.data.capabilities.agents ? "good" : "warn"}>
                    {status.data.capabilities.agents ? "configured" : "not configured"}
                  </Badge>
                </li>
                <li className="flex items-center justify-between">
                  <span className="text-slate-400">Execution mode</span>
                  <Badge tone={status.data.mode === "sandbox" ? "good" : "warn"}>
                    {status.data.mode}
                  </Badge>
                </li>
              </ul>
              <p className="mt-4 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
                Flags are computed from the environment on each request. Credentials are only marked
                verified once an OAuth token was actually issued in the sandbox.
              </p>
            </div>
          </section>

          <footer className="mono mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-4 text-[10px] text-slate-600">
            <span>
              {status.data.app} · {status.data.db.server_version ?? "db unknown"}
            </span>
            <span>checked {utc(status.data.checked_at)}</span>
          </footer>
        </>
      )}
    </main>
  );
}

import { redirect } from "next/navigation";
import { LoginForm } from "@/components/LoginForm";
import { getSystemStatus, type SystemStatus } from "@/lib/api";
import { readSession } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const session = await readSession();
  if (session) redirect("/");
  const { next } = await searchParams;

  let status: SystemStatus | null = null;
  try {
    status = await getSystemStatus();
  } catch {
    status = null;
  }

  return (
    <div className="relative grid min-h-screen overflow-hidden lg:grid-cols-[1.08fr_0.92fr]">
      <div className="login-grid relative hidden flex-col justify-between border-r border-slate-800/70 p-10 lg:flex xl:p-14">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
            <svg width="22" height="22" viewBox="0 0 16 16" fill="none" aria-hidden>
              <circle cx="8" cy="8" r="6.2" stroke="currentColor" strokeOpacity=".4" />
              <path d="m4.8 8.3 2.1 2 4.3-4.6" stroke="currentColor" strokeWidth="1.6" />
            </svg>
          </span>
          <div>
            <p className="mono text-[12px] uppercase tracking-[0.24em] text-slate-100">ResolveAI</p>
            <p className="text-[11px] text-slate-500">Autonomous dispute resolution, under human control</p>
          </div>
        </div>

        <div className="my-10 max-w-xl">
          <p className="mono text-[10px] uppercase tracking-[0.24em] text-emerald-400/80">
            PayPal AI Hackathon · agentic commerce
          </p>
          <h1 className="mt-4 text-[44px] font-semibold leading-[1.05] tracking-[-0.035em] text-slate-50 xl:text-[52px]">
            Turn disputes into
            <span className="block text-slate-400">defensible decisions.</span>
          </h1>
          <p className="mt-5 max-w-md text-[13px] leading-relaxed text-slate-400">
            Buyer and Merchant agents argue the case. The Resolution agent picks a remedy inside a
            deterministic policy envelope. A signed payment plan is the only path to money.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-3">
            {[
              ["Policy gate", "deterministic"],
              ["Human approval", "above cap"],
              ["Audit trail", "hash chained"],
            ].map(([label, hint]) => (
              <div key={label} className="rounded-lg border border-slate-800/80 bg-slate-900/30 px-3 py-2.5">
                <p className="mono text-[9px] uppercase tracking-[0.14em] text-slate-500">{label}</p>
                <p className="mt-1 text-[11px] text-slate-300">{hint}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="mono flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] text-slate-600">
          <span className="flex items-center gap-1.5">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                status?.db.connected ? "bg-emerald-400" : "bg-rose-400"
              }`}
            />
            {status?.db.connected ? "postgres connected" : "api degraded"}
          </span>
          <span>{status?.mode ?? "replay"} mode</span>
          <span>{status?.counts.disputes ?? 0} disputes</span>
          <span>{status?.counts.refunds ?? 0} refunds</span>
        </div>
      </div>

      <div className="flex items-center justify-center px-5 py-10 sm:px-8">
        <div className="w-full max-w-[400px]">
          <div className="mb-6 lg:hidden">
            <p className="mono text-[11px] uppercase tracking-[0.24em] text-slate-200">ResolveAI</p>
            <p className="mt-1 text-[11px] text-slate-500">Dispute control tower</p>
          </div>
          <p className="mono text-[10px] uppercase tracking-[0.2em] text-emerald-400/80">Merchant access</p>
          <h2 className="mt-2 text-[24px] font-semibold tracking-tight text-slate-50">Sign in to your workspace</h2>
          <p className="mt-2 text-[12px] leading-relaxed text-slate-500">
            Use the seeded Northwind merchant account. Every screen is backed by the FastAPI service and
            PostgreSQL — nothing on the dashboard is a mock.
          </p>
          <LoginForm nextPath={next} />
          <p className="mono mt-6 border-t border-slate-800/80 pt-4 text-[9px] leading-relaxed text-slate-600">
            Seeded credentials: <span className="text-slate-400">owner@northwind.example</span> /{" "}
            <span className="text-slate-400">resolveai-demo</span>
            <br />
            Change DEMO_USER_PASSWORD before exposing this deployment.
          </p>
        </div>
      </div>
    </div>
  );
}

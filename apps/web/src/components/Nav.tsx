import Link from "next/link";

export function Nav({
  mode,
  live,
  right,
}: {
  mode: string;
  live: boolean;
  right?: React.ReactNode;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-[#070b12]/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-3">
        <Link href="/" className="flex items-center gap-2.5">
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden>
            <circle cx="8" cy="8" r="6.5" stroke="#334155" />
            <path d="M5 8.4l2 1.9 4-4.6" stroke="#34d399" strokeWidth="1.4" />
          </svg>
          <span className="mono text-[11px] uppercase tracking-[0.22em] text-slate-300">
            ResolveAI
          </span>
        </Link>
        <div className="flex items-center gap-3">
          <span
            className={`mono rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
              live
                ? "border-emerald-800 bg-emerald-950/60 text-emerald-300"
                : "border-slate-700 bg-slate-900 text-slate-400"
            }`}
            title={live ? "Live PayPal sandbox credentials in use" : "Replay fixtures — no PayPal network calls"}
          >
            {mode} mode
          </span>
          {right}
        </div>
      </div>
    </header>
  );
}

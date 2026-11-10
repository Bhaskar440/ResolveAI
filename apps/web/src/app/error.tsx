"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto max-w-3xl px-6 py-24">
      <p className="mono text-xs uppercase tracking-widest text-rose-400">render error</p>
      <h1 className="mt-3 text-2xl font-semibold">The dashboard could not render.</h1>
      <pre className="mono mt-4 overflow-x-auto rounded-lg border border-rose-900/50 bg-rose-950/30 p-4 text-xs text-rose-200">
        {error.message}
      </pre>
      <button
        onClick={reset}
        className="mt-6 rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm"
      >
        Retry
      </button>
    </main>
  );
}

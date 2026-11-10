"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

export function RefreshButton({ label = "Re-check stack" }: { label?: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();

  return (
    <button
      type="button"
      onClick={() => start(() => router.refresh())}
      disabled={pending}
      className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-slate-500 hover:bg-slate-800 disabled:opacity-50"
    >
      {pending ? "Checking…" : label}
    </button>
  );
}

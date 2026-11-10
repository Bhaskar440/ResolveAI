"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { resetDemo, seedDemo } from "@/lib/api";

export function DemoControls() {
  const router = useRouter();
  const [busy, setBusy] = useState<"seed" | "reset" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: "seed" | "reset") {
    if (kind === "reset" && !window.confirm("Delete all disputes, runs, refunds and approvals?")) {
      return;
    }
    setBusy(kind);
    setError(null);
    setMessage(null);
    try {
      if (kind === "seed") {
        const res = await seedDemo();
        setMessage(`Seeded ${res.disputes} disputes from ${res.mode} fixtures.`);
      } else {
        await resetDemo();
        setMessage("Demo state cleared.");
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {message && <span className="mono hidden text-[10px] text-emerald-400 md:inline">{message}</span>}
      {error && <span className="mono hidden text-[10px] text-rose-400 md:inline">{error}</span>}
      <button
        onClick={() => run("seed")}
        disabled={busy !== null}
        className="mono rounded border border-slate-700 bg-slate-900 px-2.5 py-1 text-[10px] uppercase tracking-wider text-slate-300 hover:border-slate-500 disabled:opacity-40"
      >
        {busy === "seed" ? "seeding…" : "seed"}
      </button>
      <button
        onClick={() => run("reset")}
        disabled={busy !== null}
        className="mono rounded border border-slate-800 px-2.5 py-1 text-[10px] uppercase tracking-wider text-slate-500 hover:border-rose-800 hover:text-rose-300 disabled:opacity-40"
      >
        {busy === "reset" ? "resetting…" : "reset"}
      </button>
    </div>
  );
}

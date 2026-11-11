"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, login } from "@/lib/api";

export function LoginForm({ nextPath = "/" }: { nextPath?: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("owner@northwind.example");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      const target = nextPath.startsWith("/") && !nextPath.startsWith("//") ? nextPath : "/";
      router.replace(target);
      router.refresh();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Unable to sign in.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-8 space-y-4">
      <label className="block">
        <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">
          Work email
        </span>
        <input
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="w-full rounded-lg border border-slate-800 bg-[#080d15] px-3.5 py-2.5 text-[13px] text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-emerald-700/70 focus:ring-2 focus:ring-emerald-900/30"
          placeholder="you@merchant.com"
        />
      </label>

      <label className="block">
        <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">
          Password
        </span>
        <input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="w-full rounded-lg border border-slate-800 bg-[#080d15] px-3.5 py-2.5 text-[13px] text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-emerald-700/70 focus:ring-2 focus:ring-emerald-900/30"
          placeholder="Enter your password"
        />
      </label>

      {error && (
        <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 px-3 py-2.5 text-[12px] leading-relaxed text-rose-200">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-4 py-2.5 text-[12px] font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? "Signing in…" : "Enter control tower"}
        <span aria-hidden>→</span>
      </button>

      <button
        type="button"
        onClick={() => {
          setEmail("owner@northwind.example");
          setPassword("resolveai-demo");
          setError(null);
        }}
        className="mono w-full rounded-lg border border-slate-800 px-4 py-2 text-[10px] uppercase tracking-[0.14em] text-slate-500 transition hover:border-slate-600 hover:text-slate-300"
      >
        Use seeded demo credentials
      </button>

      <p className="mono text-center text-[9px] leading-relaxed text-slate-600">
        Demo account is created on first login · password hashed with scrypt · HttpOnly signed session
      </p>
    </form>
  );
}

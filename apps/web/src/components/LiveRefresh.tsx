"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function LiveRefresh({
  active,
  intervalMs = 3500,
  label = "live · auto-refreshing",
}: {
  active: boolean;
  intervalMs?: number;
  label?: string;
}) {
  const router = useRouter();

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => router.refresh(), intervalMs);
    return () => window.clearInterval(timer);
  }, [active, intervalMs, router]);

  if (!active) return null;

  return (
    <span className="mono inline-flex items-center gap-1.5 rounded border border-emerald-800/70 bg-emerald-950/40 px-2 py-0.5 text-[9px] uppercase tracking-wider text-emerald-300">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
      {label}
    </span>
  );
}

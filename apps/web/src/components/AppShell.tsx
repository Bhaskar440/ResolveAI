"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { logout, type AuthSession, type SystemStatus } from "@/lib/api";
import { DemoControls } from "./DemoControls";

type NavItem = { href: string; label: string; hint: string; icon: React.ReactNode };

function Icon({ name }: { name: "grid" | "cases" | "chat" | "chart" | "book" | "menu" | "close" | "logout" }) {
  const common = {
    width: 17,
    height: 17,
    viewBox: "0 0 20 20",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (name === "grid") {
    return (
      <svg {...common}>
        <rect x="3" y="3" width="5.5" height="5.5" rx="1" />
        <rect x="11.5" y="3" width="5.5" height="5.5" rx="1" />
        <rect x="3" y="11.5" width="5.5" height="5.5" rx="1" />
        <rect x="11.5" y="11.5" width="5.5" height="5.5" rx="1" />
      </svg>
    );
  }
  if (name === "cases") {
    return (
      <svg {...common}>
        <path d="M4 5.5h12M4 10h12M4 14.5h7" />
      </svg>
    );
  }
  if (name === "chat") {
    return (
      <svg {...common}>
        <path d="M4 4.5h12v8.8H8l-4 3V4.5Z" />
        <path d="M7 8h6M7 10.5h3.5" />
      </svg>
    );
  }
  if (name === "chart") {
    return (
      <svg {...common}>
        <path d="M4 16V9M9.3 16V4.5M14.6 16v-4" />
      </svg>
    );
  }
  if (name === "book") {
    return (
      <svg {...common}>
        <path d="M3.5 4.5h5A2.5 2.5 0 0 1 11 7v9a2.5 2.5 0 0 0-2.5-2.5h-5v-9Z" />
        <path d="M16.5 4.5h-3A2.5 2.5 0 0 0 11 7v9a2.5 2.5 0 0 1 2.5-2.5h3v-9Z" />
      </svg>
    );
  }
  if (name === "menu") {
    return (
      <svg {...common}>
        <path d="M3.5 5.5h13M3.5 10h13M3.5 14.5h13" />
      </svg>
    );
  }
  if (name === "close") {
    return (
      <svg {...common}>
        <path d="m5 5 10 10M15 5 5 15" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M8 8V5.5A1.5 1.5 0 0 1 9.5 4h1A1.5 1.5 0 0 1 12 5.5V8" />
      <path d="M5 8h10v7.5H5V8Z" />
      <path d="M8.5 12h3" />
    </svg>
  );
}

const NAV: NavItem[] = [
  { href: "/", label: "Overview", hint: "Operations cockpit", icon: <Icon name="grid" /> },
  { href: "/cases", label: "Cases", hint: "Dispute queue", icon: <Icon name="cases" /> },
  { href: "/complaints", label: "Complaints", hint: "Buyer workspace", icon: <Icon name="chat" /> },
  { href: "/analytics", label: "Analytics", hint: "Outcomes & refunds", icon: <Icon name="chart" /> },
  { href: "/knowledge", label: "Knowledge", hint: "Policy evidence", icon: <Icon name="book" /> },
];

function titleFor(pathname: string) {
  if (pathname === "/") return "Overview";
  if (pathname.startsWith("/cases/")) return "Case detail";
  if (pathname.startsWith("/cases")) return "Case management";
  if (pathname.startsWith("/complaints")) return "Complaint workspace";
  if (pathname.startsWith("/analytics")) return "Analytics";
  if (pathname.startsWith("/knowledge")) return "Knowledge & evidence";
  return "ResolveAI";
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function AppShell({
  session,
  status,
  children,
}: {
  session: AuthSession;
  status: SystemStatus | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const live = Boolean(status?.capabilities.live_paypal);
  const mode = status?.mode ?? session.mode ?? "offline";

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  async function signOut() {
    setSigningOut(true);
    try {
      await logout();
    } catch {
      // The cookie is HttpOnly; navigate anyway so the user is never trapped.
    } finally {
      window.location.assign("/login");
    }
  }

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-5 pb-5 pt-5">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
            <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden>
              <circle cx="8" cy="8" r="6.2" stroke="currentColor" strokeOpacity=".4" />
              <path d="m4.8 8.3 2.1 2 4.3-4.6" stroke="currentColor" strokeWidth="1.6" />
            </svg>
          </span>
          <span>
            <span className="mono block text-[11px] uppercase tracking-[0.24em] text-slate-200">
              ResolveAI
            </span>
            <span className="block text-[10px] text-slate-500">Dispute control tower</span>
          </span>
        </Link>
        <button
          onClick={() => setOpen(false)}
          className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800/70 hover:text-slate-100 lg:hidden"
          aria-label="Close navigation"
        >
          <Icon name="close" />
        </button>
      </div>

      <div className="px-3">
        <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Workspace</p>
          <p className="mt-0.5 truncate text-[12px] font-medium text-slate-200">
            {session.user.merchant_name}
          </p>
          <p className="mono mt-0.5 truncate text-[10px] text-slate-500">
            {session.user.merchant_slug} · {session.user.role}
          </p>
        </div>
      </div>

      <nav className="mt-4 flex-1 space-y-1 overflow-y-auto px-3">
        {NAV.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 transition ${
                active
                  ? "border border-emerald-500/20 bg-emerald-500/10 text-emerald-200"
                  : "border border-transparent text-slate-400 hover:bg-slate-800/50 hover:text-slate-100"
              }`}
            >
              <span className={active ? "text-emerald-300" : "text-slate-500 group-hover:text-slate-300"}>
                {item.icon}
              </span>
              <span className="min-w-0">
                <span className="block text-[12.5px] font-medium">{item.label}</span>
                <span className="block text-[10px] text-slate-500">{item.hint}</span>
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-slate-800/80 p-3">
        <div className="flex items-center justify-between px-2 pb-2">
          <span className="mono text-[9px] uppercase tracking-[0.16em] text-slate-600">Demo tools</span>
          <DemoControls />
        </div>
        <div className="flex items-center justify-between rounded-lg border border-slate-800/70 bg-slate-900/40 px-3 py-2">
          <div className="flex items-center gap-2">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                status?.db.connected ? "bg-emerald-400" : "bg-rose-400"
              }`}
            />
            <span className="mono text-[9px] uppercase tracking-wider text-slate-500">
              {status?.db.connected ? "api + postgres" : "api degraded"}
            </span>
          </div>
          <span className="mono text-[9px] text-slate-600">{status?.env ?? "local"}</span>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#070b12]">
      {open && (
        <button
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setOpen(false)}
          aria-label="Close navigation overlay"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-[264px] border-r border-slate-800/80 bg-[#080d15] transition-transform duration-200 lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sidebar}
      </aside>

      <div className="lg:pl-[264px]">
        <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-[#070b12]/90 backdrop-blur">
          <div className="flex h-14 items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <button
                onClick={() => setOpen(true)}
                className="rounded-md border border-slate-800 p-1.5 text-slate-400 hover:bg-slate-800/60 hover:text-slate-100 lg:hidden"
                aria-label="Open navigation"
              >
                <Icon name="menu" />
              </button>
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium text-slate-200">{titleFor(pathname)}</p>
                <p className="mono hidden text-[9px] uppercase tracking-[0.18em] text-slate-600 sm:block">
                  {session.user.merchant_name}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 sm:gap-3">
              <span
                className={`mono hidden rounded border px-2 py-0.5 text-[9px] uppercase tracking-wider sm:inline-flex ${
                  live
                    ? "border-emerald-800 bg-emerald-950/60 text-emerald-300"
                    : "border-slate-700 bg-slate-900 text-slate-400"
                }`}
                title={live ? "PayPal sandbox credentials active" : "Replay fixtures — no PayPal network calls"}
              >
                {mode} mode
              </span>
              <div className="hidden items-center gap-2 rounded-full border border-slate-800 bg-slate-900/60 px-2.5 py-1 sm:flex">
                <span className="grid h-6 w-6 place-items-center rounded-full bg-emerald-500/15 text-[10px] font-semibold text-emerald-300">
                  {initials(session.user.display_name)}
                </span>
                <span className="max-w-[130px] truncate text-[11px] text-slate-300">
                  {session.user.display_name}
                </span>
              </div>
              <button
                onClick={signOut}
                disabled={signingOut}
                className="mono inline-flex items-center gap-1.5 rounded-md border border-slate-800 px-2 py-1.5 text-[9px] uppercase tracking-wider text-slate-500 hover:border-slate-600 hover:text-slate-200 disabled:opacity-50"
              >
                <Icon name="logout" />
                <span className="hidden sm:inline">{signingOut ? "signing out…" : "sign out"}</span>
              </button>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}

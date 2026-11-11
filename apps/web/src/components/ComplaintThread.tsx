"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { sendCaseMessage, type DisputeMessage } from "@/lib/api";
import { utc } from "./ui";

function channelLabel(message: DisputeMessage) {
  if (message.direction === "outbound") return "merchant note · case file";
  if (message.channel === "paypal") return "buyer · via PayPal";
  return `${message.author_type} · ${message.channel}`;
}

export function ComplaintThread({
  disputeId,
  messages,
  compact = false,
}: {
  disputeId: string;
  messages: DisputeMessage[];
  compact?: boolean;
}) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const text = note.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      await sendCaseMessage(disputeId, text);
      setNote("");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {messages.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-800 bg-slate-900/20 px-4 py-5 text-[11.5px] leading-relaxed text-slate-500">
          No buyer messages were provided with this dispute. The agents reason from the reason code,
          order facts and any merchant notes you add below.
        </p>
      ) : (
        <ul className={`space-y-2.5 ${compact ? "max-h-[380px] overflow-y-auto pr-1" : ""}`}>
          {messages.map((message) => {
            const outbound = message.direction === "outbound";
            return (
              <li
                key={message.id}
                className={`rounded-lg border p-3 ${
                  outbound
                    ? "border-emerald-900/40 bg-emerald-950/15"
                    : "border-slate-800 bg-[#0a1019]"
                }`}
              >
                <div className="mono flex flex-wrap items-center justify-between gap-2 text-[9px] uppercase tracking-wider">
                  <span className={outbound ? "text-emerald-400/80" : "text-slate-500"}>
                    {channelLabel(message)}
                  </span>
                  <span className="text-slate-600">{utc(message.sent_at ?? message.created_at)}</span>
                </div>
                <p className="mt-1.5 whitespace-pre-wrap text-[12px] leading-relaxed text-slate-300">
                  {message.body}
                </p>
              </li>
            );
          })}
        </ul>
      )}

      <div className="rounded-lg border border-slate-800/80 bg-slate-900/30 p-3">
        <label className="mono mb-1.5 block text-[9px] uppercase tracking-[0.14em] text-slate-500">
          Add merchant note
        </label>
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          rows={3}
          maxLength={4000}
          placeholder="Record a response, evidence reference or next action…"
          className="mono w-full resize-none rounded-md border border-slate-800 bg-[#080d15] px-3 py-2 text-[11px] leading-relaxed text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p className="mono text-[9px] leading-relaxed text-slate-600">
            Saved to the case file · outbound PayPal messaging is not enabled in this build
          </p>
          <button
            onClick={save}
            disabled={busy || !note.trim()}
            className="mono rounded border border-emerald-800/70 bg-emerald-950/40 px-3 py-1.5 text-[9px] uppercase tracking-wider text-emerald-300 hover:bg-emerald-900/50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "saving…" : "save note"}
          </button>
        </div>
        {error && (
          <p className="mono mt-2 rounded border border-rose-900/60 bg-rose-950/30 px-2 py-1.5 text-[10px] text-rose-300">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

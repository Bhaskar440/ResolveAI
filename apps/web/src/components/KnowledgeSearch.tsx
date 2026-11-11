"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ingestKnowledge,
  searchKnowledge,
  type KnowledgeSearch as KnowledgeSearchResult,
} from "@/lib/api";

const EXAMPLES = [
  "item not received seller protection tracking",
  "not as described partial refund policy",
  "unauthorised transaction approval required",
];

export function KnowledgeSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [k, setK] = useState(5);
  const [busy, setBusy] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [result, setResult] = useState<KnowledgeSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ingestMessage, setIngestMessage] = useState<string | null>(null);

  async function search(text = query) {
    const trimmed = text.trim();
    if (trimmed.length < 2) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await searchKnowledge(trimmed, undefined, k));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function reindex() {
    if (!window.confirm("Re-ingest the policy corpus? This embeds every document again and can take a moment.")) {
      return;
    }
    setIngesting(true);
    setError(null);
    setIngestMessage(null);
    try {
      const response = await ingestKnowledge(false);
      setIngestMessage(
        `Indexed ${String(response.documents ?? "?")} document(s), ${String(response.chunks ?? "?")} chunk(s) with ${String(response.embedding_model ?? "the configured embedder")}.`,
      );
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIngesting(false);
    }
  }

  return (
    <div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") search();
          }}
          placeholder="Search policy clauses, e.g. seller protection for tracking…"
          className="mono min-w-0 flex-1 rounded-md border border-slate-800 bg-[#0a1019] px-3 py-2.5 text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
        />
        <select
          value={k}
          onChange={(event) => setK(Number(event.target.value))}
          className="mono rounded-md border border-slate-800 bg-[#0a1019] px-2.5 py-2 text-[10px] text-slate-300 outline-none focus:border-slate-600"
        >
          {[3, 4, 5, 6, 8].map((value) => (
            <option key={value} value={value}>
              top {value}
            </option>
          ))}
        </select>
        <button
          onClick={() => search()}
          disabled={busy || query.trim().length < 2}
          className="mono rounded-md border border-emerald-800/70 bg-emerald-950/40 px-4 py-2 text-[10px] uppercase tracking-wider text-emerald-300 hover:bg-emerald-900/50 disabled:opacity-40"
        >
          {busy ? "retrieving…" : "search policy"}
        </button>
        <button
          onClick={reindex}
          disabled={ingesting}
          className="mono rounded-md border border-slate-800 px-3 py-2 text-[10px] uppercase tracking-wider text-slate-500 hover:border-slate-600 hover:text-slate-300 disabled:opacity-40"
        >
          {ingesting ? "re-indexing…" : "re-index"}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            onClick={() => {
              setQuery(example);
              search(example);
            }}
            className="mono rounded border border-slate-800 bg-slate-900/40 px-2 py-1 text-[9px] text-slate-500 hover:border-slate-600 hover:text-slate-300"
          >
            {example}
          </button>
        ))}
      </div>

      {error && (
        <div className="mono mt-3 rounded border border-rose-900/60 bg-rose-950/30 px-3 py-2 text-[10px] text-rose-300">
          {error}
        </div>
      )}
      {ingestMessage && (
        <div className="mono mt-3 rounded border border-emerald-900/60 bg-emerald-950/30 px-3 py-2 text-[10px] text-emerald-300">
          {ingestMessage}
        </div>
      )}

      {result && (
        <div className="mt-4">
          <div className="mono mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[9px] uppercase tracking-wider text-slate-600">
            <span>{result.citations.length} citation(s)</span>
            <span>{result.mode}</span>
            <span>{result.embedding_model}</span>
            <span>{result.latency_ms.toFixed(0)}ms</span>
            {result.used_fallback && <span className="text-amber-400/80">fallback embedder</span>}
          </div>
          {result.warning && (
            <p className="mono mb-2 rounded border border-amber-900/50 bg-amber-950/20 px-2 py-1.5 text-[9px] text-amber-300/80">
              {result.warning}
            </p>
          )}
          <div className="space-y-2.5">
            {result.citations.map((citation) => (
              <div key={citation.chunk_id} className="rounded-lg border border-slate-800/80 bg-[#0a1019] p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-[11.5px] font-medium text-slate-200">
                      {citation.document} · {citation.section}
                    </p>
                    <p className="mono mt-0.5 text-[8.5px] text-slate-600">
                      {citation.chunk_id} · {citation.source} · {citation.retrieval_mode}
                    </p>
                  </div>
                  <span className="mono rounded border border-cyan-900/60 bg-cyan-950/30 px-1.5 py-0.5 text-[8px] uppercase tracking-wider text-cyan-300">
                    score {citation.score.toFixed(3)}
                  </span>
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{citation.text}</p>
              </div>
            ))}
            {result.citations.length === 0 && (
              <p className="rounded border border-dashed border-slate-800 px-3 py-6 text-center text-[11px] text-slate-500">
                No policy clause matched that query.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

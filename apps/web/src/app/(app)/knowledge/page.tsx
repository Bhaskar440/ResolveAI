import { KnowledgeSearch } from "@/components/KnowledgeSearch";
import { RefreshButton } from "@/components/RefreshButton";
import {
  getKnowledgeDocuments,
  getKnowledgeStatus,
  getPolicyRules,
  type KnowledgeDocuments,
  type KnowledgeStatus,
  type PolicyRules,
} from "@/lib/api";
import { formatMoney, Meter, PageHeader, Panel, utc } from "@/components/ui";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function KnowledgePage() {
  let status: KnowledgeStatus | null = null;
  let documents: KnowledgeDocuments | null = null;
  let rules: PolicyRules | null = null;
  let error: string | null = null;

  try {
    [status, documents, rules] = await Promise.all([
      getKnowledgeStatus(),
      getKnowledgeDocuments(),
      getPolicyRules(),
    ]);
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  const maxCategory = Math.max(1, ...(status?.categories.map((row) => row.documents) ?? [1]));

  return (
    <>
      <PageHeader
        eyebrow="Evidence & policy"
        title="Knowledge base"
        description="Policy clauses are embedded with Gemini and stored in PostgreSQL + pgvector. The Resolution agent cites the exact clause text; this page exposes the same corpus and retrieval API for inspection."
        actions={<RefreshButton label="Refresh knowledge" />}
      />

      {error && (
        <div className="mb-4 rounded-xl border border-rose-900/60 bg-rose-950/30 p-4">
          <p className="mono text-[10px] uppercase tracking-wider text-rose-300">knowledge unavailable</p>
          <p className="mt-1 text-[12px] text-rose-100">{error}</p>
        </div>
      )}

      {status && (
        <>
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["Corpus status", status.ready ? "ready" : "not indexed", status.pgvector_version ? `pgvector ${status.pgvector_version}` : "pgvector missing"],
              ["Documents", String(status.documents), `${status.chunks} chunks`],
              ["Embedding model", status.settings.embedding_model, `${status.settings.dimensions} dimensions · top ${status.settings.top_k}`],
              ["Last ingested", status.last_ingested_at ? utc(status.last_ingested_at) : "—", "document updated_at"],
            ].map(([label, value, hint]) => (
              <div key={label} className="card rounded-xl px-4 py-3.5">
                <p className="mono text-[9px] uppercase tracking-[0.16em] text-slate-500">{label}</p>
                <p className={`mt-1.5 truncate text-[19px] font-semibold leading-none tracking-tight ${label === "Corpus status" ? (status.ready ? "text-emerald-300" : "text-amber-300") : "text-slate-100"}`}>
                  {value}
                </p>
                <p className="mono mt-1.5 truncate text-[9px] text-slate-600">{hint}</p>
              </div>
            ))}
          </section>

          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(330px,0.8fr)]">
            <Panel title="Policy retrieval" subtitle="live pgvector cosine search">
              <KnowledgeSearch />
            </Panel>

            <div className="space-y-5">
              <Panel title="Categories" subtitle="indexed documents">
                <div className="space-y-3">
                  {status.categories.map((row) => (
                    <div key={row.category}>
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="mono text-[9px] uppercase tracking-wider text-slate-400">{row.category}</span>
                        <span className="mono text-[10px] text-slate-300">{row.documents}</span>
                      </div>
                      <Meter value={row.documents} max={maxCategory} tone="violet" />
                    </div>
                  ))}
                  {status.categories.length === 0 && <p className="text-[11px] text-slate-500">No documents indexed.</p>}
                </div>
              </Panel>

              <Panel title="Embeddings" subtitle="model used per chunk">
                <div className="space-y-2">
                  {status.embedding_models.map((row) => (
                    <div key={row.model} className="flex items-center justify-between gap-2 rounded-lg border border-slate-800/80 bg-slate-900/30 px-3 py-2">
                      <span className="mono truncate text-[9.5px] text-slate-400">{row.model}</span>
                      <span className="mono text-[10px] text-slate-200">{row.chunks}</span>
                    </div>
                  ))}
                  {status.embedding_models.length === 0 && <p className="text-[11px] text-slate-500">No embeddings yet.</p>}
                </div>
              </Panel>
            </div>
          </div>

          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(330px,0.8fr)]">
            <Panel title="Indexed documents" subtitle="exact corpus metadata">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[620px] border-collapse text-left">
                  <thead>
                    <tr className="mono border-b border-slate-800 text-[9px] uppercase tracking-wider text-slate-600">
                      <th className="pb-2 font-medium">Document</th>
                      <th className="pb-2 font-medium">Category</th>
                      <th className="pb-2 text-right font-medium">Chunks</th>
                      <th className="pb-2 text-right font-medium">Version</th>
                      <th className="pb-2 text-right font-medium">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(documents?.documents ?? []).map((document) => (
                      <tr key={document.id} className="border-b border-slate-800/60 last:border-0">
                        <td className="py-2.5 pr-3">
                          <p className="text-[11px] text-slate-300">{document.title}</p>
                          <p className="mono mt-0.5 text-[8.5px] text-slate-600">{document.source_key}</p>
                        </td>
                        <td className="mono py-2.5 text-[9px] uppercase tracking-wider text-slate-500">{document.category}</td>
                        <td className="mono py-2.5 text-right text-[10px] text-slate-300">{document.chunk_count}</td>
                        <td className="mono py-2.5 text-right text-[10px] text-slate-400">{document.version}</td>
                        <td className="mono py-2.5 text-right text-[9px] text-slate-500">{utc(document.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {(documents?.documents ?? []).length === 0 && (
                <p className="py-6 text-center text-[11px] text-slate-500">No documents indexed yet.</p>
              )}
            </Panel>

            <Panel title="Policy envelope" subtitle={rules ? `rules v${rules.version}` : "live rules"}>
              <dl className="space-y-2.5 text-[11px]">
                {rules && (
                  <>
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">Autonomous refund cap</dt>
                      <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.auto_resolve_cap))}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">Autonomous offer cap</dt>
                      <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.auto_offer_cap))}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">Hard cap — human</dt>
                      <dd className="mono text-slate-200">{formatMoney(String(rules.thresholds.hard_cap))}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">Fraud reasons</dt>
                      <dd className="mono text-right text-[9px] text-slate-300">{rules.fraud_reasons.join(", ")}</dd>
                    </div>
                  </>
                )}
              </dl>
              <p className="mt-4 border-t border-slate-800 pt-3 text-[10.5px] leading-relaxed text-slate-500">
                Retrieval suggests policy text; the deterministic gate remains the source of truth for money movement.
              </p>
            </Panel>
          </div>
        </>
      )}
    </>
  );
}

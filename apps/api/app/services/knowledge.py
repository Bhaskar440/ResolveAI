"""PostgreSQL + pgvector knowledge base.

Ingests the merchant policy corpus (markdown), chunks it by heading, embeds the
chunks with Gemini, and stores vectors in pgvector. Retrieval embeds the case
query and ranks chunks by cosine distance. When the embedding API or the
database is unavailable the service degrades to labelled lexical retrieval —
it never fabricates citations.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import PolicyCitation
from app.agents.embeddings import Embedder, EmbeddingError, get_embedder
from app.agents.rag import (
    PolicyChunk as LocalChunk,
)
from app.agents.rag import (
    chunk_document,
    content_hash,
    load_documents,
    rank_chunks,
    retrieve_policies,
)
from app.core.config import get_settings
from app.db.models import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger("resolveai.knowledge")
settings = get_settings()

HASH_MODEL = "hash-768"
VECTOR_DISTANCE_MIN_SCORE = 0.05


class KnowledgeIngestError(RuntimeError):
    pass


@dataclass
class RetrievalResult:
    citations: list[PolicyCitation] = field(default_factory=list)
    query: str = ""
    mode: str = "none"
    embedding_model: str = ""
    warning: str | None = None
    latency_ms: int = 0

    @property
    def used_fallback(self) -> bool:
        return self.mode in {"lexical", "local-lexical", "none"}

    def meta(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "embedding_model": self.embedding_model,
            "used_fallback": self.used_fallback,
            "warning": self.warning,
            "latency_ms": self.latency_ms,
            "citation_ids": [citation.chunk_id for citation in self.citations],
        }


async def _existing_model(session: AsyncSession) -> str | None:
    return (
        await session.execute(select(KnowledgeChunk.embedding_model).limit(1))
    ).scalar_one_or_none()


async def _health_check(embedder: Embedder) -> None:
    if embedder.kind != "gemini":
        return
    await embedder.embed(["policy retrieval health check"])


async def ingest_knowledge(
    session: AsyncSession, *, force: bool = False, allow_fallback: bool = True
) -> dict[str, Any]:
    """Idempotently ingest the markdown corpus into pgvector.

    Unchanged documents are skipped by content hash. Re-indexing a document
    replaces its chunks atomically. A failing embedding API falls back to the
    deterministic hash embedder only when no vector index exists yet, so a
    corpus never mixes incompatible vector spaces.
    """
    documents = load_documents()
    if not documents:
        raise KnowledgeIngestError("No policy markdown files found in app/agents/knowledge.")

    existing_model = await _existing_model(session)
    preferred = existing_model or settings.knowledge_embedding_model
    warning: str | None = None
    mode = "vector"

    try:
        embedder = get_embedder(preferred)
        await _health_check(embedder)
    except EmbeddingError as exc:
        if existing_model and existing_model != HASH_MODEL:
            # Do not replace a working Gemini index with hashed vectors.
            raise KnowledgeIngestError(
                f"Embedding API unavailable; keeping existing {existing_model} index: {exc}"
            ) from exc
        if not allow_fallback:
            raise
        warning = f"Embedding API unavailable ({exc}); indexed with deterministic {HASH_MODEL} fallback."
        logger.warning(warning)
        embedder = get_embedder(HASH_MODEL)
        mode = "hash-fallback"

    prepared: list[tuple[Any, list[Any]]] = []
    skipped = 0
    for document in documents:
        chunks = chunk_document(
            document,
            max_chars=settings.knowledge_chunk_chars,
            overlap=settings.knowledge_chunk_overlap,
        )
        digest = content_hash(document.text)
        current = (
            await session.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.source_key == document.source_key)
            )
        ).scalar_one_or_none()
        if (
            not force
            and current
            and current.content_hash == digest
            and current.chunk_count == len(chunks)
            and current.embedding_model == embedder.name
        ):
            skipped += 1
            continue
        prepared.append((document, chunks))

    if not prepared:
        result = {
            "documents": len(documents),
            "chunks": 0,
            "skipped": skipped,
            "embedding_model": existing_model or embedder.name,
            "mode": mode,
            "warning": warning,
        }
        await session.commit()
        return result

    texts = [
        f"{chunk.section}\n{chunk.text}" for _document, chunks in prepared for chunk in chunks
    ]
    try:
        vectors = await embedder.embed(texts)
    except EmbeddingError as exc:
        if existing_model and existing_model != HASH_MODEL:
            raise KnowledgeIngestError(
                f"Embedding API failed during re-index; existing {existing_model} index preserved: {exc}"
            ) from exc
        if not allow_fallback:
            raise
        warning = f"Embedding API failed ({exc}); this ingestion used {HASH_MODEL} fallback."
        logger.warning(warning)
        embedder = get_embedder(HASH_MODEL)
        vectors = await embedder.embed(texts)
        mode = "hash-fallback"

    total_chunks = 0
    vector_cursor = 0
    for document, chunks in prepared:
        digest = content_hash(document.text)
        stored = (
            await session.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.source_key == document.source_key)
            )
        ).scalar_one_or_none()
        if stored is None:
            stored = KnowledgeDocument(
                source_key=document.source_key,
                title=document.title,
                category=document.category,
                version=document.version,
                content_hash=digest,
                raw_text=document.text,
                chunk_count=len(chunks),
                embedding_model=embedder.name,
            )
            session.add(stored)
            await session.flush()
        else:
            stored.title = document.title
            stored.category = document.category
            stored.version = document.version
            stored.content_hash = digest
            stored.raw_text = document.text
            stored.chunk_count = len(chunks)
            stored.embedding_model = embedder.name
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == stored.id)
            )

        for chunk in chunks:
            session.add(
                KnowledgeChunk(
                    document_id=stored.id,
                    chunk_index=chunk.chunk_index,
                    section_title=chunk.section,
                    citation_id=chunk.chunk_id,
                    content=chunk.text,
                    token_count=len(chunk.text.split()),
                    content_hash=content_hash(chunk.text),
                    embedding=vectors[vector_cursor],
                    embedding_model=embedder.name,
                )
            )
            vector_cursor += 1
            total_chunks += 1

    await session.commit()
    return {
        "documents": len(documents),
        "chunks": total_chunks,
        "skipped": skipped,
        "embedding_model": embedder.name,
        "mode": mode,
        "warning": warning,
    }


def build_case_query(case: dict, extra: str | None = None) -> str:
    """Build a retrieval query from the dispute, not from a hardcoded template."""
    parts = [
        str(case.get("reason_code") or ""),
        str(case.get("reason_detail") or ""),
        f"amount {case.get('amount')} {case.get('currency')}",
    ]
    order = case.get("order") or {}
    if order.get("item_title"):
        parts.append(str(order["item_title"]))
    for message in case.get("messages") or []:
        if message.get("body"):
            parts.append(str(message["body"]))
    shipping = case.get("shipping") or {}
    if shipping:
        parts.append(
            "shipping "
            + " ".join(
                str(shipping.get(key))
                for key in ("carrier", "tracking_number", "status")
                if shipping.get(key)
            )
        )
    if extra:
        parts.append(extra)
    return " ".join(part for part in parts if part).strip()[:4000]


async def _vector_search(
    session: AsyncSession, vector: list[float], *, k: int
) -> list[tuple[float, KnowledgeChunk, KnowledgeDocument]]:
    distance = KnowledgeChunk.embedding.cosine_distance(vector)
    rows = (
        await session.execute(
            select(KnowledgeChunk, KnowledgeDocument, distance.label("distance"))
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .order_by(distance)
            .limit(max(k * 2, k))
        )
    ).all()
    hits: list[tuple[float, KnowledgeChunk, KnowledgeDocument]] = []
    for chunk, document, dist in rows:
        score = 1.0 - float(dist)
        if score >= VECTOR_DISTANCE_MIN_SCORE:
            hits.append((score, chunk, document))
    return hits[:k]


def _citation(score: float, chunk: KnowledgeChunk, document: KnowledgeDocument, *, mode: str) -> PolicyCitation:
    return PolicyCitation(
        chunk_id=chunk.citation_id,
        title=chunk.section_title,
        text=chunk.content[:1600],
        score=round(score, 4),
        source=document.source_key,
        document=document.title,
        section=chunk.section_title,
        category=document.category,
        retrieval_mode=mode,
        embedding_model=chunk.embedding_model,
    )


async def _database_lexical(
    session: AsyncSession, query: str, *, reason_code: str | None, k: int
) -> list[PolicyCitation]:
    rows = (
        await session.execute(
            select(KnowledgeChunk, KnowledgeDocument).join(
                KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id
            )
        )
    ).all()
    local = [
        LocalChunk(
            chunk_id=chunk.citation_id,
            document=document.title,
            section=chunk.section_title,
            category=document.category,
            text=chunk.content,
            source=document.source_key,
            chunk_index=chunk.chunk_index,
        )
        for chunk, document in rows
    ]
    hits = rank_chunks(query, local, reason_code=reason_code, k=k)
    return [
        PolicyCitation(
            chunk_id=item.chunk_id,
            title=item.section,
            text=item.text[:1600],
            score=round(score, 4),
            source=item.source,
            document=item.document,
            section=item.section,
            category=item.category,
            retrieval_mode="postgres-lexical",
            embedding_model="lexical",
        )
        for score, item in hits
    ]


async def retrieve_policy_citations(
    session: AsyncSession,
    case: dict,
    *,
    query: str | None = None,
    reason_code: str | None = None,
    k: int | None = None,
) -> RetrievalResult:
    """Retrieve source-attributed policy citations for a dispute case."""
    started = time.perf_counter()
    settings_k = k or settings.knowledge_top_k
    resolved_query = query or build_case_query(case)
    resolved_reason = reason_code or str(case.get("reason_code") or "")
    warnings: list[str] = []

    chunk_count = (await session.execute(select(func.count()).select_from(KnowledgeChunk))).scalar() or 0
    if chunk_count == 0:
        citations = retrieve_policies(
            resolved_query, reason_code=resolved_reason, k=settings_k
        )
        return RetrievalResult(
            citations=citations,
            query=resolved_query,
            mode="local-lexical",
            embedding_model="",
            warning="Knowledge base is empty; used local markdown lexical retrieval.",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    model = (await session.execute(select(KnowledgeChunk.embedding_model).limit(1))).scalar_one_or_none()
    vector: list[float] | None = None
    try:
        embedder = get_embedder(model or settings.knowledge_embedding_model)
        vector = await embedder.embed_one(resolved_query)
    except EmbeddingError as exc:
        warnings.append(f"Query embedding failed ({exc}); using lexical retrieval.")
        logger.warning("query embedding failed: %s", exc)

    if vector is not None:
        try:
            hits = await _vector_search(session, vector, k=settings_k)
        except Exception as exc:  # noqa: BLE001 - DB/extension failure must degrade, not crash
            warnings.append(f"pgvector search failed ({exc}); using lexical retrieval.")
            logger.warning("pgvector search failed: %s", exc)
            hits = []
        if hits:
            citations = [
                _citation(score, chunk, document, mode="vector")
                for score, chunk, document in hits
            ]
            return RetrievalResult(
                citations=citations,
                query=resolved_query,
                mode="vector",
                embedding_model=model or settings.knowledge_embedding_model,
                warning="; ".join(warnings) or None,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        warnings.append("Vector search returned no chunk above the relevance floor.")

    lexical = await _database_lexical(session, resolved_query, reason_code=resolved_reason, k=settings_k)
    if lexical:
        return RetrievalResult(
            citations=lexical,
            query=resolved_query,
            mode="lexical",
            embedding_model="lexical",
            warning="; ".join(warnings) or None,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    citations = retrieve_policies(resolved_query, reason_code=resolved_reason, k=settings_k)
    warnings.append("No database matches; used local markdown lexical retrieval.")
    return RetrievalResult(
        citations=citations,
        query=resolved_query,
        mode="local-lexical",
        embedding_model="",
        warning="; ".join(warnings),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


async def knowledge_status(session: AsyncSession) -> dict[str, Any]:
    extension = (
        await session.execute(
            text("select extversion from pg_extension where extname = 'vector'")
        )
    ).scalar_one_or_none()
    documents = (
        await session.execute(select(func.count()).select_from(KnowledgeDocument))
    ).scalar() or 0
    chunks = (
        await session.execute(select(func.count()).select_from(KnowledgeChunk))
    ).scalar() or 0
    categories = (
        await session.execute(
            select(KnowledgeDocument.category, func.count())
            .group_by(KnowledgeDocument.category)
            .order_by(KnowledgeDocument.category)
        )
    ).all()
    models = (
        await session.execute(
            select(KnowledgeChunk.embedding_model, func.count())
            .group_by(KnowledgeChunk.embedding_model)
            .order_by(KnowledgeChunk.embedding_model)
        )
    ).all()
    last_ingested = (
        await session.execute(select(func.max(KnowledgeDocument.updated_at)))
    ).scalar_one_or_none()
    return {
        "ready": bool(extension) and chunks > 0,
        "pgvector_version": extension,
        "documents": documents,
        "chunks": chunks,
        "categories": [{"category": category, "documents": count} for category, count in categories],
        "embedding_models": [{"model": model, "chunks": count} for model, count in models],
        "last_ingested_at": last_ingested.isoformat() if last_ingested else None,
        "settings": {
            "embedding_model": settings.knowledge_embedding_model,
            "dimensions": settings.knowledge_embedding_dimensions,
            "top_k": settings.knowledge_top_k,
            "chunk_chars": settings.knowledge_chunk_chars,
            "chunk_overlap": settings.knowledge_chunk_overlap,
        },
    }


async def ensure_knowledge_base(session: AsyncSession) -> dict[str, Any] | None:
    """Seed the corpus once for the demo; never overwrite an existing index."""
    try:
        chunks = (
            await session.execute(select(func.count()).select_from(KnowledgeChunk))
        ).scalar() or 0
        if chunks:
            return None
        return await ingest_knowledge(session)
    except Exception as exc:  # noqa: BLE001 - startup/demo seeding must not take the API down
        logger.warning("knowledge base seeding skipped: %s", exc)
        await session.rollback()
        return {"error": str(exc)[:500]}

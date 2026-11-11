"""Knowledge base API: ingest, status and retrieval preview."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import SessionDep, require_session
from app.core.errors import AppError
from app.db.models import KnowledgeDocument
from app.services.knowledge import (
    KnowledgeIngestError,
    ingest_knowledge,
    knowledge_status,
    retrieve_policy_citations,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class IngestRequest(BaseModel):
    force: bool = False
    allow_fallback: bool = True


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=4000)
    reason_code: str | None = None
    k: int = Field(default=4, ge=1, le=12)


@router.get("/status")
async def status(session: SessionDep) -> dict[str, Any]:
    return await knowledge_status(session)


@router.get("/documents")
async def documents(session: SessionDep) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                select(KnowledgeDocument).order_by(
                    KnowledgeDocument.category.asc(), KnowledgeDocument.title.asc()
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": len(rows),
        "documents": [
            {
                "id": str(doc.id),
                "title": doc.title,
                "source_key": doc.source_key,
                "category": doc.category,
                "version": doc.version,
                "chunk_count": doc.chunk_count,
                "embedding_model": doc.embedding_model,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            for doc in rows
        ],
    }


@router.post("/ingest", dependencies=[Depends(require_session)])
async def ingest(session: SessionDep, body: IngestRequest | None = None) -> dict[str, Any]:
    request = body or IngestRequest()
    try:
        return await ingest_knowledge(
            session, force=request.force, allow_fallback=request.allow_fallback
        )
    except KnowledgeIngestError as exc:
        raise AppError(
            str(exc), status_code=503, code="KNOWLEDGE_INGEST_FAILED"
        ) from exc


@router.post("/search", dependencies=[Depends(require_session)])
async def search(session: SessionDep, body: SearchRequest) -> dict[str, Any]:
    case = {
        "reason_code": body.reason_code or "",
        "reason_detail": body.query,
        "amount": "0",
        "currency": "USD",
    }
    result = await retrieve_policy_citations(
        session,
        case,
        query=body.query,
        reason_code=body.reason_code,
        k=body.k,
    )
    return {
        "citations": [citation.model_dump() for citation in result.citations],
        "query": result.query,
        "mode": result.mode,
        "embedding_model": result.embedding_model,
        "used_fallback": result.used_fallback,
        "warning": result.warning,
        "latency_ms": result.latency_ms,
    }

"""Policy corpus parsing, chunking and deterministic lexical retrieval.

The production path embeds these chunks into pgvector and searches by cosine
distance (see `app/services/knowledge.py`). This module keeps a local lexical
fallback for offline tests and for honest degradation when embeddings or the
database are unavailable.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.agents.contracts import PolicyCitation

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were", "with",
}


def _tokens(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 2]


def _slug(text: str) -> str:
    return "-".join(TOKEN_RE.findall(text.lower()))[:80]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PolicyDocument:
    source_key: str
    title: str
    category: str
    version: str
    text: str


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    document: str
    section: str
    category: str
    text: str
    source: str
    chunk_index: int
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def title(self) -> str:
        return self.section


def _metadata(text: str) -> tuple[dict[str, str], str]:
    metadata: dict[str, str] = {}
    body_lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z]+):\s*(.+)$", line.strip())
        if match and match.group(1).lower() in {"title", "category", "version"}:
            metadata[match.group(1).lower()] = match.group(2).strip()
        else:
            body_lines.append(line)
    return metadata, "\n".join(body_lines)


def parse_document(path: Path) -> PolicyDocument:
    text = path.read_text(encoding="utf-8")
    metadata, body = _metadata(text)
    title = metadata.get("title")
    if not title:
        first_heading = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), None)
        title = first_heading or path.stem.replace("-", " ").title()
    return PolicyDocument(
        source_key=path.name,
        title=title,
        category=metadata.get("category") or path.stem.replace("-policy", "").replace("-", "_"),
        version=metadata.get("version", "1"),
        text=body,
    )


def _sections(document: PolicyDocument) -> list[tuple[str, str, tuple[str, ...]]]:
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    body: list[str] = []
    for line in document.text.splitlines():
        if line.startswith("## "):
            if current_title is not None:
                sections.append((current_title, body))
            current_title = line[3:].strip()
            body = []
        elif current_title is not None:
            body.append(line)
    if current_title is not None:
        sections.append((current_title, body))

    parsed: list[tuple[str, str, tuple[str, ...]]] = []
    for title, lines in sections:
        tags: tuple[str, ...] = ()
        kept: list[str] = []
        for line in lines:
            if line.lower().startswith("tags:"):
                tags = tuple(_tokens(line.split(":", 1)[1]))
            else:
                kept.append(line)
        text = "\n".join(kept).strip()
        if text:
            parsed.append((title, text, tags))
    return parsed


def _split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= max_chars:
        return [text] if text else []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            step = max(1, max_chars - overlap)
            for start in range(0, len(sentence), step):
                piece = sentence[start : start + max_chars].strip()
                if piece:
                    chunks.append(piece)
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = sentence
    if current:
        chunks.append(current.strip())
    return chunks


def chunk_document(
    document: PolicyDocument, *, max_chars: int = 1400, overlap: int = 150
) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    index = 0
    for section_title, section_text, tags in _sections(document):
        for piece in _split_text(section_text, max_chars, overlap):
            chunks.append(
                PolicyChunk(
                    chunk_id=f"{_slug(document.source_key.rsplit('.', 1)[0])}:{_slug(section_title)}",
                    document=document.title,
                    section=section_title,
                    category=document.category,
                    text=piece,
                    source=document.source_key,
                    chunk_index=index,
                    tags=tags,
                )
            )
            index += 1
    return chunks


@lru_cache(maxsize=1)
def load_documents() -> tuple[PolicyDocument, ...]:
    return tuple(parse_document(path) for path in sorted(KNOWLEDGE_DIR.glob("*.md")))


@lru_cache(maxsize=1)
def load_policy_chunks() -> tuple[PolicyChunk, ...]:
    chunks: list[PolicyChunk] = []
    for document in load_documents():
        chunks.extend(chunk_document(document))
    return tuple(chunks)


def _score(query_tokens: set[str], reason_tokens: set[str], chunk: PolicyChunk) -> float:
    body_tokens = _tokens(f"{chunk.section} {chunk.text}")
    if not body_tokens:
        return 0.0
    counts: dict[str, int] = {}
    for token in body_tokens:
        counts[token] = counts.get(token, 0) + 1
    score = sum(
        (counts[token] / math.sqrt(len(body_tokens))) for token in query_tokens if token in counts
    )
    score += 2.5 * len(reason_tokens & set(chunk.tags))
    return score


def rank_chunks(
    query: str,
    chunks: list[PolicyChunk],
    *,
    reason_code: str | None = None,
    k: int = 4,
) -> list[tuple[float, PolicyChunk]]:
    query_tokens = set(_tokens(f"{query} {reason_code or ''}"))
    reason_tokens = set(_tokens(reason_code or ""))
    scored = [(score, chunk) for chunk in chunks if (score := _score(query_tokens, reason_tokens, chunk)) > 0]
    scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
    return scored[: max(1, k)]


def retrieve_policies(
    query: str, *, reason_code: str | None = None, k: int = 4
) -> list[PolicyCitation]:
    """Local lexical retrieval used when PostgreSQL/embeddings are unavailable."""
    hits = rank_chunks(query, list(load_policy_chunks()), reason_code=reason_code, k=k)
    return [
        PolicyCitation(
            chunk_id=chunk.chunk_id,
            title=chunk.section,
            text=chunk.text[:1600],
            score=round(score, 4),
            source=chunk.source,
            document=chunk.document,
            section=chunk.section,
            category=chunk.category,
            retrieval_mode="local-lexical",
            embedding_model="",
        )
        for score, chunk in hits
    ]

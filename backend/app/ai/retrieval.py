"""Tenant-scoped, deterministic knowledge grounding.

Reuses Phase 3's PostgreSQL full-text search (to_tsvector/plainto_tsquery/
ts_rank) — no new search technology, no embeddings, zero additional cost.
Deliberately filters out chunks belonging to an inactive
`KnowledgeDocument` here, in this Phase 4 service, rather than changing
`KnowledgeChunkRepository.search()` or the existing Phase 3
`/knowledge/search` route — that route's behavior (which does not filter
by document status) is a pre-existing Phase 3 gap, out of scope to change
here without risking an unreviewed behavior change to already-shipped
API. See docs/PROGRESS.md's Phase 4 section for the note.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.providers.base import RetrievedSource
from app.models.enums import ContentStatus
from app.repositories.faq import FAQRepository
from app.repositories.knowledge import KnowledgeChunkRepository, KnowledgeDocumentRepository

EXCERPT_MAX_CHARS = 300
TITLE_MAX_CHARS = 200


def _truncate(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    limit: int


def retrieve(db: Session, *, tenant_id: uuid.UUID, query: RetrievalQuery) -> list[RetrievedSource]:
    """Strictly tenant-filtered (every repository call is constructed with
    `tenant_id`), active-content-only, bounded in both result count and
    excerpt length, with deterministic ordering for equal scores (sorted by
    score desc, then by source_id as a stable tiebreaker — never left to
    incidental SQL/row order)."""

    if not query.text.strip():
        return []

    faq_repo = FAQRepository(db, tenant_id)
    chunk_repo = KnowledgeChunkRepository(db, tenant_id)
    document_repo = KnowledgeDocumentRepository(db, tenant_id)

    sources: list[RetrievedSource] = []

    for faq, score in faq_repo.search(query.text, limit=query.limit):
        sources.append(
            RetrievedSource(
                source_id=f"faq:{faq.id}",
                source_type="faq",
                title=_truncate(faq.question, TITLE_MAX_CHARS),
                excerpt=_truncate(faq.answer, EXCERPT_MAX_CHARS),
                score=score,
                metadata={"category": faq.category} if faq.category else {},
            )
        )

    for chunk, score in chunk_repo.search(query.text, limit=query.limit):
        document = document_repo.get(chunk.document_id)
        if document is None or document.status != ContentStatus.ACTIVE:
            continue
        sources.append(
            RetrievedSource(
                source_id=f"knowledge_chunk:{chunk.id}",
                source_type="knowledge_chunk",
                title=_truncate(document.title, TITLE_MAX_CHARS),
                excerpt=_truncate(chunk.content, EXCERPT_MAX_CHARS),
                score=score,
                metadata={"document_id": str(document.id), "chunk_index": chunk.chunk_index},
            )
        )

    # Deterministic ordering for equal scores: never rely on incidental SQL
    # row order once results from two separate queries are merged.
    sources.sort(key=lambda s: (-s.score, s.source_id))
    return sources[: query.limit]

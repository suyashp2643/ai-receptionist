import re
import uuid

from sqlalchemy.orm import Session

from app.models.enums import UNSUPPORTED_KNOWLEDGE_SOURCE_TYPES, ContentStatus, KnowledgeSourceType
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource
from app.repositories.knowledge import (
    KnowledgeChunkRepository,
    KnowledgeDocumentRepository,
    KnowledgeSourceRepository,
)

# Deterministic, fixed-size chunking with a small overlap so a sentence
# spanning a boundary is still findable from either chunk. No embeddings,
# no external service — just plain string slicing.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

_WHITESPACE_RUN = re.compile(r"\s+")


class UnsupportedKnowledgeSourceTypeError(ValueError):
    def __init__(self, source_type: KnowledgeSourceType):
        self.source_type = source_type
        super().__init__(
            f"Knowledge source type {source_type.value!r} is not implemented yet — "
            "only 'manual' is supported in this phase."
        )


def create_source(db: Session, *, tenant_id: uuid.UUID, type_: KnowledgeSourceType, title: str) -> KnowledgeSource:
    if type_ in UNSUPPORTED_KNOWLEDGE_SOURCE_TYPES:
        raise UnsupportedKnowledgeSourceTypeError(type_)
    source = KnowledgeSource(tenant_id=tenant_id, type=type_, title=title)
    KnowledgeSourceRepository(db, tenant_id).add(source)
    db.flush()
    return source


def chunk_text(raw_text: str) -> list[str]:
    """Deterministic local chunking — same input always produces the same
    chunks. Collapses whitespace first so chunk boundaries are stable
    regardless of the source's original line wrapping."""
    normalized = _WHITESPACE_RUN.sub(" ", raw_text.strip())
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    step = CHUNK_SIZE - CHUNK_OVERLAP
    while start < len(normalized):
        end = min(start + CHUNK_SIZE, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start += step
    return chunks


def create_document(
    db: Session, *, tenant_id: uuid.UUID, source: KnowledgeSource, title: str, raw_text: str
) -> tuple[KnowledgeDocument, list[KnowledgeChunk]]:
    document = KnowledgeDocument(tenant_id=tenant_id, source_id=source.id, title=title, raw_text=raw_text)
    KnowledgeDocumentRepository(db, tenant_id).add(document)
    db.flush()

    chunks = _create_chunks(db, tenant_id=tenant_id, document=document, raw_text=raw_text)
    return document, chunks


def _create_chunks(
    db: Session, *, tenant_id: uuid.UUID, document: KnowledgeDocument, raw_text: str
) -> list[KnowledgeChunk]:
    chunk_repo = KnowledgeChunkRepository(db, tenant_id)
    chunks = []
    for index, content in enumerate(chunk_text(raw_text)):
        chunk = KnowledgeChunk(tenant_id=tenant_id, document_id=document.id, content=content, chunk_index=index)
        chunk_repo.add(chunk)
        chunks.append(chunk)
    db.flush()
    return chunks


def replace_document_text(
    db: Session, *, tenant_id: uuid.UUID, document: KnowledgeDocument, raw_text: str
) -> list[KnowledgeChunk]:
    """Chunks are always fully regenerated, never edited in place — keeps
    chunk_index deterministic and avoids partial/stale chunk states."""
    document.raw_text = raw_text
    KnowledgeChunkRepository(db, tenant_id).delete_for_document(document.id)
    db.flush()
    return _create_chunks(db, tenant_id=tenant_id, document=document, raw_text=raw_text)


def deactivate_document(db: Session, *, tenant_id: uuid.UUID, document: KnowledgeDocument) -> None:
    document.status = ContentStatus.INACTIVE


def delete_document(db: Session, *, tenant_id: uuid.UUID, document: KnowledgeDocument) -> None:
    KnowledgeChunkRepository(db, tenant_id).delete_for_document(document.id)
    db.delete(document)

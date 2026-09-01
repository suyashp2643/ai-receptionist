import uuid

from sqlalchemy import delete, func, select

from app.models.enums import ContentStatus
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource
from app.repositories.base import TenantScopedRepository


class KnowledgeSourceRepository(TenantScopedRepository[KnowledgeSource]):  # type: ignore[type-var]
    model = KnowledgeSource


class KnowledgeDocumentRepository(TenantScopedRepository[KnowledgeDocument]):  # type: ignore[type-var]
    model = KnowledgeDocument

    def list_active(self) -> list[KnowledgeDocument]:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == self.tenant_id,
            KnowledgeDocument.status == ContentStatus.ACTIVE,
        )
        return list(self.db.scalars(stmt).all())


class KnowledgeChunkRepository(TenantScopedRepository[KnowledgeChunk]):  # type: ignore[type-var]
    model = KnowledgeChunk

    def list_for_document(self, document_id: uuid.UUID) -> list[KnowledgeChunk]:
        stmt = (
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.tenant_id == self.tenant_id,
                KnowledgeChunk.document_id == document_id,
            )
            .order_by(KnowledgeChunk.chunk_index)
        )
        return list(self.db.scalars(stmt).all())

    def delete_for_document(self, document_id: uuid.UUID) -> None:
        stmt = delete(KnowledgeChunk).where(
            KnowledgeChunk.tenant_id == self.tenant_id, KnowledgeChunk.document_id == document_id
        )
        self.db.execute(stmt)

    def search(self, query: str, *, limit: int = 10) -> list[tuple[KnowledgeChunk, float]]:
        """Deterministic, local, zero-cost search using PostgreSQL's built-in
        full-text search (no embeddings, no external service, no vector DB).
        Always scoped to self.tenant_id — never leaks across tenants."""
        tsvector = func.to_tsvector("english", KnowledgeChunk.content)
        tsquery = func.plainto_tsquery("english", query)
        rank = func.ts_rank(tsvector, tsquery).label("rank")

        stmt = (
            select(KnowledgeChunk, rank)
            .where(KnowledgeChunk.tenant_id == self.tenant_id, tsvector.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(limit)
        )
        return [(row[0], float(row[1])) for row in self.db.execute(stmt).all()]

from sqlalchemy import func, select

from app.models.faq import FAQ
from app.repositories.base import TenantScopedRepository


class FAQRepository(TenantScopedRepository[FAQ]):  # type: ignore[type-var]
    model = FAQ

    def list_ordered(self) -> list[FAQ]:
        stmt = select(FAQ).where(FAQ.tenant_id == self.tenant_id).order_by(FAQ.display_order, FAQ.created_at)
        return list(self.db.scalars(stmt).all())

    def search(self, query: str, *, limit: int = 10) -> list[tuple[FAQ, float]]:
        """Same full-text-search approach as KnowledgeChunkRepository —
        matches against the question and answer combined, active FAQs
        only. Introduced for Phase 4 grounding; Phase 3 never needed a
        ranked search over FAQs (only exact-match duplicate detection)."""
        combined = func.concat(FAQ.question, " ", FAQ.answer)
        tsvector = func.to_tsvector("english", combined)
        tsquery = func.plainto_tsquery("english", query)
        rank = func.ts_rank(tsvector, tsquery).label("rank")

        stmt = (
            select(FAQ, rank)
            .where(FAQ.tenant_id == self.tenant_id, FAQ.is_active.is_(True), tsvector.op("@@")(tsquery))
            .order_by(rank.desc(), FAQ.id)
            .limit(limit)
        )
        return [(row[0], float(row[1])) for row in self.db.execute(stmt).all()]

    def find_similar_question(self, question: str) -> FAQ | None:
        """Deterministic, exact-normalized-match duplicate check (case/whitespace
        insensitive) — not fuzzy matching, so results are predictable."""
        normalized = " ".join(question.strip().lower().split())
        stmt = select(FAQ).where(FAQ.tenant_id == self.tenant_id)
        for faq in self.db.scalars(stmt).all():
            if " ".join(faq.question.strip().lower().split()) == normalized:
                return faq
        return None

from sqlalchemy import select

from app.models.faq import FAQ
from app.repositories.base import TenantScopedRepository


class FAQRepository(TenantScopedRepository[FAQ]):  # type: ignore[type-var]
    model = FAQ

    def list_ordered(self) -> list[FAQ]:
        stmt = select(FAQ).where(FAQ.tenant_id == self.tenant_id).order_by(FAQ.display_order, FAQ.created_at)
        return list(self.db.scalars(stmt).all())

    def find_similar_question(self, question: str) -> FAQ | None:
        """Deterministic, exact-normalized-match duplicate check (case/whitespace
        insensitive) — not fuzzy matching, so results are predictable."""
        normalized = " ".join(question.strip().lower().split())
        stmt = select(FAQ).where(FAQ.tenant_id == self.tenant_id)
        for faq in self.db.scalars(stmt).all():
            if " ".join(faq.question.strip().lower().split()) == normalized:
                return faq
        return None

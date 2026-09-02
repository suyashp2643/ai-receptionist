import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.models.human_handoff import HumanHandoff
from app.repositories.base import TenantScopedRepository


class HumanHandoffRepository(TenantScopedRepository[HumanHandoff]):  # type: ignore[type-var]
    model = HumanHandoff

    def list_recent(self, *, limit: int, offset: int) -> Sequence[HumanHandoff]:
        stmt = (
            select(HumanHandoff)
            .where(HumanHandoff.tenant_id == self.tenant_id)
            .order_by(HumanHandoff.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all()

    def get_by_idempotency_key(self, idempotency_key: str) -> HumanHandoff | None:
        stmt = select(HumanHandoff).where(
            HumanHandoff.tenant_id == self.tenant_id,
            HumanHandoff.idempotency_key == idempotency_key,
        )
        return self.db.scalars(stmt).first()

    def list_by_conversation_id(self, conversation_id: uuid.UUID) -> Sequence[HumanHandoff]:
        stmt = select(HumanHandoff).where(
            HumanHandoff.tenant_id == self.tenant_id,
            HumanHandoff.conversation_id == conversation_id,
        )
        return self.db.scalars(stmt).all()

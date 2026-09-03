import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, func, or_, select, update

from app.models.contact import Contact
from app.models.enums import HandoffStatus
from app.models.human_handoff import HumanHandoff
from app.repositories.base import TenantScopedRepository

HANDOFF_SORT_COLUMNS = {
    "created_at": HumanHandoff.created_at,
    "updated_at": HumanHandoff.updated_at,
}


@dataclass(frozen=True)
class HandoffFilters:
    receptionist_id: uuid.UUID | None = None
    statuses: tuple[HandoffStatus, ...] | None = None
    urgency: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    search: str | None = None


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

    def list_by_contact_id(self, contact_id: uuid.UUID) -> Sequence[HumanHandoff]:
        stmt = select(HumanHandoff).where(
            HumanHandoff.tenant_id == self.tenant_id, HumanHandoff.contact_id == contact_id
        )
        return self.db.scalars(stmt).all()

    def list_dashboard(
        self,
        *,
        filters: HandoffFilters,
        sort_column: str,
        sort_descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[HumanHandoff], int]:
        conditions = [HumanHandoff.tenant_id == self.tenant_id]
        if filters.receptionist_id is not None:
            conditions.append(HumanHandoff.receptionist_id == filters.receptionist_id)
        if filters.statuses:
            conditions.append(HumanHandoff.status.in_(filters.statuses))
        if filters.urgency:
            conditions.append(HumanHandoff.urgency == filters.urgency)
        if filters.created_after is not None:
            conditions.append(HumanHandoff.created_at >= filters.created_after)
        if filters.created_before is not None:
            conditions.append(HumanHandoff.created_at < filters.created_before)
        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            contact_match = exists(
                select(Contact.id).where(
                    Contact.tenant_id == self.tenant_id,
                    Contact.id == HumanHandoff.contact_id,
                    or_(
                        Contact.name.ilike(pattern),
                        Contact.normalized_email.ilike(pattern),
                        Contact.normalized_phone.ilike(pattern),
                    ),
                )
            )
            conditions.append(contact_match)

        total = self.db.scalar(select(func.count()).select_from(HumanHandoff).where(*conditions)) or 0
        sort_col = HANDOFF_SORT_COLUMNS[sort_column]
        order = sort_col.desc() if sort_descending else sort_col.asc()
        stmt = select(HumanHandoff).where(*conditions).order_by(order, HumanHandoff.id).limit(limit).offset(offset)
        return self.db.scalars(stmt).all(), total

    def claim_atomically(self, handoff_id: uuid.UUID, *, actor_user_id: uuid.UUID) -> bool:
        """The real defense against two users claiming the same handoff: one
        conditional UPDATE, gated on `status == OPEN` in the WHERE clause
        itself — never a SELECT-then-check-then-UPDATE, which would leave a
        race window between the check and the write. Returns True only if
        this call's UPDATE actually matched a row (i.e. this call won the
        race); a concurrent second caller's identical statement matches zero
        rows and gets False, no exception, no lock held."""
        stmt = (
            update(HumanHandoff)
            .where(
                HumanHandoff.id == handoff_id,
                HumanHandoff.tenant_id == self.tenant_id,
                HumanHandoff.status == HandoffStatus.OPEN,
            )
            .values(status=HandoffStatus.CLAIMED, assigned_user_id=actor_user_id, version=HumanHandoff.version + 1)
        )
        result = self.db.execute(stmt)
        return result.rowcount == 1

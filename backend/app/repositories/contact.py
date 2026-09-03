import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select

from app.models.contact import Contact
from app.repositories.base import TenantScopedRepository


class ContactRepository(TenantScopedRepository[Contact]):  # type: ignore[type-var]
    model = Contact

    def get_by_conversation_id(self, conversation_id: uuid.UUID) -> Contact | None:
        stmt = (
            select(Contact)
            .where(Contact.tenant_id == self.tenant_id, Contact.conversation_id == conversation_id)
            .order_by(Contact.created_at.desc())
        )
        return self.db.scalars(stmt).first()

    def list_recent(self, *, limit: int, offset: int) -> Sequence[Contact]:
        stmt = (
            select(Contact)
            .where(Contact.tenant_id == self.tenant_id)
            .order_by(Contact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all()

    def list_dashboard(
        self,
        *,
        created_after: datetime | None,
        created_before: datetime | None,
        search: str | None,
        sort_descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Contact], int]:
        conditions = [Contact.tenant_id == self.tenant_id]
        if created_after is not None:
            conditions.append(Contact.created_at >= created_after)
        if created_before is not None:
            conditions.append(Contact.created_at < created_before)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Contact.name.ilike(pattern),
                    Contact.normalized_email.ilike(pattern),
                    Contact.normalized_phone.ilike(pattern),
                )
            )

        total = self.db.scalar(select(func.count()).select_from(Contact).where(*conditions)) or 0
        order = Contact.created_at.desc() if sort_descending else Contact.created_at.asc()
        stmt = select(Contact).where(*conditions).order_by(order, Contact.id).limit(limit).offset(offset)
        return self.db.scalars(stmt).all(), total

    def get_by_normalized_email(self, normalized_email: str) -> Contact | None:
        stmt = select(Contact).where(
            Contact.tenant_id == self.tenant_id,
            Contact.normalized_email == normalized_email,
        )
        return self.db.scalars(stmt).first()

    def get_by_normalized_phone(self, normalized_phone: str) -> Contact | None:
        stmt = select(Contact).where(
            Contact.tenant_id == self.tenant_id,
            Contact.normalized_phone == normalized_phone,
        )
        return self.db.scalars(stmt).first()

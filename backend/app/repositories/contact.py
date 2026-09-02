import uuid
from collections.abc import Sequence

from sqlalchemy import select

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

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.models.enquiry import Enquiry
from app.repositories.base import TenantScopedRepository


class EnquiryRepository(TenantScopedRepository[Enquiry]):  # type: ignore[type-var]
    model = Enquiry

    def list_recent(self, *, limit: int, offset: int) -> Sequence[Enquiry]:
        stmt = (
            select(Enquiry)
            .where(Enquiry.tenant_id == self.tenant_id)
            .order_by(Enquiry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all()

    def get_by_conversation_id(self, conversation_id: uuid.UUID) -> Enquiry | None:
        stmt = select(Enquiry).where(
            Enquiry.tenant_id == self.tenant_id,
            Enquiry.conversation_id == conversation_id,
        )
        return self.db.scalars(stmt).first()

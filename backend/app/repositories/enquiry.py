import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, func, or_, select

from app.models.contact import Contact
from app.models.enquiry import Enquiry
from app.models.enums import EnquiryStatus
from app.repositories.base import TenantScopedRepository

ENQUIRY_SORT_COLUMNS = {
    "created_at": Enquiry.created_at,
    "updated_at": Enquiry.updated_at,
}


@dataclass(frozen=True)
class EnquiryFilters:
    receptionist_id: uuid.UUID | None = None
    statuses: tuple[EnquiryStatus, ...] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    search: str | None = None


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

    def list_by_contact_id(self, contact_id: uuid.UUID) -> Sequence[Enquiry]:
        stmt = select(Enquiry).where(Enquiry.tenant_id == self.tenant_id, Enquiry.contact_id == contact_id)
        return self.db.scalars(stmt).all()

    def get_by_conversation_id(self, conversation_id: uuid.UUID) -> Enquiry | None:
        stmt = select(Enquiry).where(
            Enquiry.tenant_id == self.tenant_id,
            Enquiry.conversation_id == conversation_id,
        )
        return self.db.scalars(stmt).first()

    def list_dashboard(
        self,
        *,
        filters: EnquiryFilters,
        sort_column: str,
        sort_descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Enquiry], int]:
        conditions = [Enquiry.tenant_id == self.tenant_id]
        if filters.receptionist_id is not None:
            conditions.append(Enquiry.receptionist_id == filters.receptionist_id)
        if filters.statuses:
            conditions.append(Enquiry.status.in_(filters.statuses))
        if filters.created_after is not None:
            conditions.append(Enquiry.created_at >= filters.created_after)
        if filters.created_before is not None:
            conditions.append(Enquiry.created_at < filters.created_before)
        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            contact_match = exists(
                select(Contact.id).where(
                    Contact.tenant_id == self.tenant_id,
                    Contact.id == Enquiry.contact_id,
                    or_(
                        Contact.name.ilike(pattern),
                        Contact.normalized_email.ilike(pattern),
                        Contact.normalized_phone.ilike(pattern),
                    ),
                )
            )
            conditions.append(contact_match)

        total = self.db.scalar(select(func.count()).select_from(Enquiry).where(*conditions)) or 0
        sort_col = ENQUIRY_SORT_COLUMNS[sort_column]
        order = sort_col.desc() if sort_descending else sort_col.asc()
        stmt = select(Enquiry).where(*conditions).order_by(order, Enquiry.id).limit(limit).offset(offset)
        return self.db.scalars(stmt).all(), total

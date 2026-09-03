import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, func, or_, select

from app.models.appointment_request import AppointmentRequest
from app.models.contact import Contact
from app.models.enums import AppointmentRequestStatus
from app.repositories.base import TenantScopedRepository

APPOINTMENT_SORT_COLUMNS = {
    "created_at": AppointmentRequest.created_at,
    "requested_date": AppointmentRequest.requested_date,
}


@dataclass(frozen=True)
class AppointmentRequestFilters:
    receptionist_id: uuid.UUID | None = None
    statuses: tuple[AppointmentRequestStatus, ...] | None = None
    requested_date_after: date | None = None
    requested_date_before: date | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    search: str | None = None


class AppointmentRequestRepository(TenantScopedRepository[AppointmentRequest]):  # type: ignore[type-var]
    model = AppointmentRequest

    def list_recent(self, *, limit: int, offset: int) -> Sequence[AppointmentRequest]:
        stmt = (
            select(AppointmentRequest)
            .where(AppointmentRequest.tenant_id == self.tenant_id)
            .order_by(AppointmentRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all()

    def get_by_idempotency_key(self, idempotency_key: str) -> AppointmentRequest | None:
        stmt = select(AppointmentRequest).where(
            AppointmentRequest.tenant_id == self.tenant_id,
            AppointmentRequest.idempotency_key == idempotency_key,
        )
        return self.db.scalars(stmt).first()

    def list_by_conversation_id(self, conversation_id: uuid.UUID) -> Sequence[AppointmentRequest]:
        stmt = select(AppointmentRequest).where(
            AppointmentRequest.tenant_id == self.tenant_id,
            AppointmentRequest.conversation_id == conversation_id,
        )
        return self.db.scalars(stmt).all()

    def list_by_contact_id(self, contact_id: uuid.UUID) -> Sequence[AppointmentRequest]:
        stmt = select(AppointmentRequest).where(
            AppointmentRequest.tenant_id == self.tenant_id, AppointmentRequest.contact_id == contact_id
        )
        return self.db.scalars(stmt).all()

    def list_dashboard(
        self,
        *,
        filters: AppointmentRequestFilters,
        sort_column: str,
        sort_descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[AppointmentRequest], int]:
        conditions = [AppointmentRequest.tenant_id == self.tenant_id]
        if filters.receptionist_id is not None:
            conditions.append(AppointmentRequest.receptionist_id == filters.receptionist_id)
        if filters.statuses:
            conditions.append(AppointmentRequest.status.in_(filters.statuses))
        if filters.requested_date_after is not None:
            conditions.append(AppointmentRequest.requested_date >= filters.requested_date_after)
        if filters.requested_date_before is not None:
            conditions.append(AppointmentRequest.requested_date <= filters.requested_date_before)
        if filters.created_after is not None:
            conditions.append(AppointmentRequest.created_at >= filters.created_after)
        if filters.created_before is not None:
            conditions.append(AppointmentRequest.created_at < filters.created_before)
        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            contact_match = exists(
                select(Contact.id).where(
                    Contact.tenant_id == self.tenant_id,
                    Contact.id == AppointmentRequest.contact_id,
                    or_(
                        Contact.name.ilike(pattern),
                        Contact.normalized_email.ilike(pattern),
                        Contact.normalized_phone.ilike(pattern),
                    ),
                )
            )
            conditions.append(contact_match)

        total = self.db.scalar(select(func.count()).select_from(AppointmentRequest).where(*conditions)) or 0
        sort_col = APPOINTMENT_SORT_COLUMNS[sort_column]
        order = sort_col.desc() if sort_descending else sort_col.asc()
        stmt = (
            select(AppointmentRequest)
            .where(*conditions)
            .order_by(order, AppointmentRequest.id)
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all(), total

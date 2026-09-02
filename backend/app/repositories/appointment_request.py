import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.models.appointment_request import AppointmentRequest
from app.repositories.base import TenantScopedRepository


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

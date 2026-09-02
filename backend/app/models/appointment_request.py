import uuid
from datetime import date, time

from sqlalchemy import Date, ForeignKey, ForeignKeyConstraint, String, Time
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AppointmentRequestStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AppointmentRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned. A REQUEST only — there is no live calendar in Phase 5,
    so this can never be silently treated as a confirmed booking. Every
    visitor-facing surface must say "pending confirmation", never
    "confirmed", until a future phase's real calendar integration sets
    status to CONFIRMED through an explicit tenant action."""

    __tablename__ = "appointment_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "receptionist_id"],
            ["receptionists.tenant_id", "receptionists.id"],
            ondelete="CASCADE",
            name="fk_appointment_requests_tenant_receptionist",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    receptionist_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    # Same-tenant validity for location_id/service_id is enforced in
    # app/services/appointment_request_service.py at write time (the same
    # pattern Phase 3 uses for Service.location_id) — a plain FK alone
    # cannot express "must belong to the same tenant as this request".
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("business_locations.id", ondelete="SET NULL")
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL")
    )

    requested_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_time: Mapped[time | None] = mapped_column(Time)
    requested_time_window: Mapped[str | None] = mapped_column(String(50))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))

    status: Mapped[AppointmentRequestStatus] = mapped_column(
        SAEnum(
            AppointmentRequestStatus,
            name="appointment_request_status",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=AppointmentRequestStatus.PENDING,
    )

    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    def __repr__(self) -> str:
        return f"AppointmentRequest(id={self.id!r}, tenant_id={self.tenant_id!r}, status={self.status!r})"

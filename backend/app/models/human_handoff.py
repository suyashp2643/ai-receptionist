import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import HandoffStatus, PreferredContactMethod
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class HumanHandoff(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned. Records a request for a human to follow up — it never
    calls, messages, or notifies anyone; Phase 5 has no delivery
    mechanism. Never a substitute for the safety engine's clinic emergency
    response (app/ai/safety.py): the orchestrator always evaluates safety
    before any handoff/action flow, and a handoff form is never presented
    as, or reachable in place of, the emergency-guidance path."""

    __tablename__ = "human_handoffs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "receptionist_id"],
            ["receptionists.tenant_id", "receptionists.id"],
            ondelete="CASCADE",
            name="fk_human_handoffs_tenant_receptionist",
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

    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    urgency: Mapped[str | None] = mapped_column(String(20))
    preferred_contact_method: Mapped[PreferredContactMethod | None] = mapped_column(
        SAEnum(
            PreferredContactMethod,
            name="preferred_contact_method",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        )
    )

    status: Mapped[HandoffStatus] = mapped_column(
        SAEnum(
            HandoffStatus,
            name="handoff_status",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=HandoffStatus.OPEN,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    def __repr__(self) -> str:
        return f"HumanHandoff(id={self.id!r}, tenant_id={self.tenant_id!r}, status={self.status!r})"

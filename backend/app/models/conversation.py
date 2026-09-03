import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ConversationChannel, ConversationMode, ConversationStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned. Phase 4 only ever creates `mode=TEST` rows — no API
    field lets a client request `future_live`; that value exists purely so
    a later phase's live/public conversations don't need a migration to add
    it. `receptionist_id` is protected by a composite foreign key against
    `receptionists(tenant_id, id)` (not just `id`), so a conversation can
    never reference a receptionist belonging to a different tenant, even at
    the database level — a real-estate for defense-in-depth on top of the
    application-layer tenant-scoped lookup every route already performs."""

    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "receptionist_id"],
            ["receptionists.tenant_id", "receptionists.id"],
            ondelete="CASCADE",
            name="fk_conversations_tenant_receptionist",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    receptionist_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    mode: Mapped[ConversationMode] = mapped_column(
        SAEnum(
            ConversationMode,
            name="conversation_mode",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=ConversationMode.TEST,
    )
    channel: Mapped[ConversationChannel] = mapped_column(
        SAEnum(
            ConversationChannel,
            name="conversation_channel",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=ConversationChannel.DASHBOARD_TEST,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(
            ConversationStatus,
            name="conversation_status",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=ConversationStatus.ACTIVE,
    )

    visitor_reference: Mapped[str | None] = mapped_column(String(200))
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="en")

    # Set once, never cleared, by the orchestrator (app/ai/orchestrator.py)
    # the first time a safety directive fires in this conversation — lets
    # Phase 6's dashboard/analytics query for safety events and clinic
    # emergencies without loading every message's `safety_labels` JSONB.
    # `had_clinic_emergency` is a stricter subset of `had_safety_event`
    # (only the "clinic_urgent" category) so a clinic emergency conversation
    # can be surfaced separately from an ordinary safety intervention, per
    # docs/security.md's requirement that emergencies never look like an
    # everyday handoff.
    had_safety_event: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    had_clinic_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    collected_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    missing_required_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    qualification_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safety_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_error_code: Mapped[str | None] = mapped_column(String(100))

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"Conversation(id={self.id!r}, tenant_id={self.tenant_id!r}, status={self.status!r})"

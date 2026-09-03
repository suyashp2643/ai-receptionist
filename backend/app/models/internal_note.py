import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class InternalNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned, staff-only annotation attached to exactly one
    operational record. Deliberately five nullable typed foreign keys
    rather than a polymorphic (entity_type, entity_id) pair: a plain FK
    gives real referential integrity (a note can never dangle, and
    `ondelete="CASCADE"` cleans it up automatically with its parent),
    which a generic polymorphic column cannot express at the database
    level — matching this codebase's established defense-in-depth
    preference (see Conversation's composite tenant/receptionist FK).
    The `CHECK` constraint below enforces "exactly one target" so a note
    can never silently apply to more than one record, or none.

    NEVER read by the AI orchestrator and NEVER served to the public widget
    — there is no route anywhere that exposes this table to a visitor or
    includes it in conversation context. See docs/security.md."""

    __tablename__ = "internal_notes"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(conversation_id, contact_id, enquiry_id, appointment_request_id, human_handoff_id) = 1",
            name="ck_internal_notes_exactly_one_target",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("enquiries.id", ondelete="CASCADE"), index=True
    )
    appointment_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("appointment_requests.id", ondelete="CASCADE"), index=True
    )
    human_handoff_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("human_handoffs.id", ondelete="CASCADE"), index=True
    )

    # Plain text only — rendered escaped in the dashboard, never as HTML.
    # Bounded at the schema layer (app/schemas/notes.py), matching every
    # other free-text column in this codebase.
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Soft-delete only — a note is never hard-deleted, so a deletion is
    # itself auditable (an ActivityEvent is recorded) and cannot silently
    # erase what a colleague already read. Every read query filters
    # `deleted_at IS NULL`.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"InternalNote(id={self.id!r}, tenant_id={self.tenant_id!r})"

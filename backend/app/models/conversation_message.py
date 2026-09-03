import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ConversationMessageRole
from app.models.mixins import UUIDPrimaryKeyMixin

# Deliberately no TimestampMixin — a message is immutable once written
# (corrections are new messages/tool events, never edits), so there is no
# `updated_at` to track, mirroring KnowledgeChunk's precedent from Phase 3.


class ConversationMessage(UUIDPrimaryKeyMixin, Base):
    """Tenant-owned. `sequence_number` gives a stable, gap-tolerant ordering
    per conversation independent of `created_at` (clock skew/equal
    timestamps under fast automated turns must never reorder a transcript).
    `idempotency_key` plus the partial unique index below is the mechanism
    that makes a retried POST .../messages safe to resubmit without
    duplicating the user's message."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index("uq_conversation_messages_sequence", "conversation_id", "sequence_number", unique=True),
        Index(
            "uq_conversation_messages_idempotency_key",
            "conversation_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    role: Mapped[ConversationMessageRole] = mapped_column(
        SAEnum(
            ConversationMessageRole,
            name="conversation_message_role",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
    )
    # Bounded at the schema layer (app/schemas/conversation.py), not here —
    # consistent with every other free-text column in this codebase.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    tool_name: Mapped[str | None] = mapped_column(String(100))
    tool_call_id: Mapped[str | None] = mapped_column(String(100))
    tool_input: Mapped[dict | None] = mapped_column(JSONB)
    tool_output: Mapped[dict | None] = mapped_column(JSONB)

    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    safety_labels: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Set by the orchestrator when this ASSISTANT message's content matches
    # one of the mock provider's known "found nothing" markers (see
    # app/ai/providers/mock.py::FALLBACK_RESPONSE_MARKERS) — Phase 6's
    # "unanswered / fallback responses" analytics metric. Always False for
    # USER/TOOL/SYSTEM messages.
    is_fallback_response: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict | None] = mapped_column(JSONB)

    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"ConversationMessage(id={self.id!r}, conversation_id={self.conversation_id!r}, "
            f"role={self.role!r}, sequence_number={self.sequence_number!r})"
        )

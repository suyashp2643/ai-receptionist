import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ConversationSummary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned, one row per conversation (enforced by the unique
    constraint on conversation_id) — created once, on completion. Phase 4
    never executes `recommended_next_action`; it is presentation-only,
    chosen from the receptionist workflow's `enabled_actions`."""

    __tablename__ = "conversation_summaries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    captured_requirements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    unresolved_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommended_next_action: Mapped[str | None] = mapped_column(String(100))
    generated_by_provider: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"ConversationSummary(id={self.id!r}, conversation_id={self.conversation_id!r})"

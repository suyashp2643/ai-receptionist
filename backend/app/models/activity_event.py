import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin

# Deliberately no TimestampMixin — an activity event is immutable and has
# no `updated_at` to track (append-only, like ConversationMessage).


class ActivityEvent(UUIDPrimaryKeyMixin, Base):
    """Tenant-owned, append-only operational audit log. Written only by
    application services performing a dashboard action (see
    app/services/activity_service.py::record) — there is no route that
    creates, edits, or deletes these directly, and no public-widget code
    path ever touches this table. `entity_id` is a plain UUID with no FK:
    an audit record must survive the deletion of the thing it describes
    (e.g. a cascade-deleted conversation), so it is intentionally NOT
    referentially tied to the row it references. `metadata_` never holds a
    secret, token, password hash, or full message/transcript body — only
    small, safe, already-public-within-the-tenant summary fields (e.g. an
    old/new status pair)."""

    __tablename__ = "activity_events"
    __table_args__ = (Index("ix_activity_events_tenant_entity", "tenant_id", "entity_type", "entity_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable: a small number of events are system-generated (none in
    # Phase 6 yet, but the column must not force a fake actor).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    event_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"ActivityEvent(id={self.id!r}, tenant_id={self.tenant_id!r}, action_type={self.action_type!r})"

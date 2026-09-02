import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class WidgetVisitorSession(UUIDPrimaryKeyMixin, Base):
    """The real authorization boundary for a public widget conversation —
    not `public_id` (see WidgetInstallation), not the browser's `Origin`
    header (abuse reduction only, spoofable by non-browser clients). The
    raw capability token is a `secrets.token_urlsafe` value returned to the
    browser exactly once, at session creation; only its SHA-256 hash is
    ever persisted (identical pattern to RefreshToken.token_hash). Every
    subsequent request presents the raw token in a header, it is rehashed
    and looked up here — never stored, logged, or echoed back raw again.

    Scoped to exactly one `(widget_installation_id, conversation_id)` pair,
    so a valid token for one visitor's conversation can never be used to
    read or write a different conversation, even one belonging to the same
    installation or the same underlying tenant.
    """

    __tablename__ = "widget_visitor_sessions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    widget_installation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("widget_installations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # never include the origin raw token
        return f"WidgetVisitorSession(id={self.id!r}, conversation_id={self.conversation_id!r})"

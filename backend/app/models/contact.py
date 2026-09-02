import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import PreferredContactMethod
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned. `marketing_consent` is a distinct, never-inferred flag
    from the mere act of providing contact details to get a reply to a
    direct enquiry — see app/services/contact_service.py's docstring for
    why these are kept structurally separate rather than one boolean."""

    __tablename__ = "contacts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable + SET NULL: a contact must survive the conversation that
    # first captured it (it may be reused/found across later chats).
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL")
    )

    name: Mapped[str | None] = mapped_column(String(200))
    normalized_email: Mapped[str | None] = mapped_column(String(320), index=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    preferred_contact_method: Mapped[PreferredContactMethod | None] = mapped_column(
        SAEnum(
            PreferredContactMethod,
            name="preferred_contact_method",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        )
    )

    marketing_consent: Mapped[bool] = mapped_column(nullable=False, default=False)
    consent_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[str] = mapped_column(String(50), nullable=False, default="widget")

    def __repr__(self) -> str:
        return f"Contact(id={self.id!r}, tenant_id={self.tenant_id!r})"

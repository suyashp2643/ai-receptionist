import uuid

from sqlalchemy import Boolean, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import EnquiryStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Enquiry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned, local-only record of qualification captured during a
    conversation (widget or test). Phase 5 scope: a durable snapshot for
    the tenant to review — see docs/database-schema.md's Phase 4 note on
    why `collected_data`-style JSONB is used rather than a field-value
    table. NOT integrated with Revenue Brain or any external CRM."""

    __tablename__ = "enquiries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "receptionist_id"],
            ["receptionists.tenant_id", "receptionists.id"],
            ondelete="CASCADE",
            name="fk_enquiries_tenant_receptionist",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    receptionist_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    source: Mapped[str] = mapped_column(String(50), nullable=False, default="widget")
    status: Mapped[EnquiryStatus] = mapped_column(
        SAEnum(
            EnquiryStatus,
            name="enquiry_status",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=EnquiryStatus.NEW,
    )

    qualification_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    qualification_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recommended_next_action: Mapped[str | None] = mapped_column(String(50))

    def __repr__(self) -> str:
        return f"Enquiry(id={self.id!r}, tenant_id={self.tenant_id!r}, status={self.status!r})"

import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ReceptionistStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Receptionist(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned. No AI execution happens here in Phase 3 — this is
    identity/branding/config only. Multiple receptionists per tenant are
    supported by this schema even though onboarding only creates one."""

    __tablename__ = "receptionists"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    industry_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("industry_templates.id", ondelete="SET NULL")
    )
    template_version: Mapped[int | None] = mapped_column(Integer)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    welcome_message: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    tone: Mapped[str | None] = mapped_column(String(50))
    default_language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    supported_languages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    accent_color: Mapped[str | None] = mapped_column(String(7))
    suggested_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[ReceptionistStatus] = mapped_column(
        SAEnum(
            ReceptionistStatus,
            name="receptionist_status",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=ReceptionistStatus.DRAFT,
    )

    def __repr__(self) -> str:
        return f"Receptionist(id={self.id!r}, tenant_id={self.tenant_id!r}, name={self.name!r})"

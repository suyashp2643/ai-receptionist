import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import OnboardingStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BusinessProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned public business details — separate from Tenant (the auth/
    workspace identity) so login/account concerns never mix with public
    business-facing content."""

    __tablename__ = "business_profiles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    business_name: Mapped[str | None] = mapped_column(String(200))
    short_description: Mapped[str | None] = mapped_column(String(1000))
    website_url: Mapped[str | None] = mapped_column(String(500))
    public_email: Mapped[str | None] = mapped_column(String(320))
    public_phone: Mapped[str | None] = mapped_column(String(20))

    industry_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("industry_templates.id", ondelete="SET NULL")
    )

    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    default_language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    supported_languages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        SAEnum(
            OnboardingStatus,
            name="onboarding_status",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=OnboardingStatus.NOT_STARTED,
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"BusinessProfile(tenant_id={self.tenant_id!r})"

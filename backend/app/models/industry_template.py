from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IndustryTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Global, read-only-to-tenants catalog data. Never tenant-owned.

    Versioned by (key, version): editing a template's content means adding a
    new version row, never mutating an existing one — so a tenant that
    already selected version N is unaffected by a later version N+1.
    """

    __tablename__ = "industry_templates"
    __table_args__ = (UniqueConstraint("key", "version", name="uq_industry_templates_key_version"),)

    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    icon: Mapped[str] = mapped_column(String(64), nullable=False)

    default_terminology: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    default_welcome_message: Mapped[str] = mapped_column(String(1000), nullable=False)
    default_suggested_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    default_qualification_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    default_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    default_safety_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    default_workflow: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"IndustryTemplate(key={self.key!r}, version={self.version!r})"

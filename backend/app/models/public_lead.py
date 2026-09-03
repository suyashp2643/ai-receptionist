from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PublicLead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A submission from the public marketing site's contact/demo-request
    form (Phase 7). Global, not tenant-owned — mirrors IndustryTemplate's
    shape, not a synthetic "platform tenant": a lead is not yet a customer
    and must never be forced under an arbitrary tenant just to satisfy a
    tenant_id foreign key.

    Never exposed through any public API — see docs/security.md's Phase 7
    threat model. There is no admin/read endpoint in Phase 7; an operator
    retrieves submissions with a direct, local-only database query (see
    docs/local-development.md), which is the documented operational
    limitation until a properly scoped internal admin surface exists.
    """

    __tablename__ = "public_leads"

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=False)
    company_size: Mapped[str] = mapped_column(String(50), nullable=False)
    estimated_monthly_volume: Mapped[str] = mapped_column(String(50), nullable=False)
    primary_use_case: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(5000), nullable=False)

    # Contact consent is required to submit at all (enforced in the schema/
    # service, not just the UI); marketing consent is a separate, optional
    # opt-in — the two must never be conflated into one checkbox.
    contact_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Truncated hash, same privacy rationale as the widget rate limiter
    # (app/core/client_identity.py) — never the raw IP, kept only for basic
    # abuse investigation during local development.
    submitted_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"PublicLead(id={self.id!r}, normalized_email={self.normalized_email!r})"

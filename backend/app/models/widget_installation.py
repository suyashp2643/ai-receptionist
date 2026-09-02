import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import WidgetInstallationStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# 32 bytes -> ~43 url-safe base64 characters. Not a secret (see the model
# docstring): revocable, unguessable enough to deter casual enumeration,
# but the actual security boundary for any conversation is the visitor
# capability token (WidgetVisitorSession), never this identifier.
_PUBLIC_ID_BYTES = 24


def generate_public_id() -> str:
    return secrets.token_urlsafe(_PUBLIC_ID_BYTES)


class WidgetInstallation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned. One row per embeddable-widget install (a tenant may
    run more than one, e.g. per site or per receptionist).

    `public_id` is what appears in the embed snippet and every public API
    URL — deliberately NOT the internal `id`/tenant UUID, so the snippet
    never reveals internal identifiers. It is revocable (rotate by
    generating a new one and updating the snippet) but is not treated as a
    high-value secret: it is visible in every embedding page's HTML
    source, by design. Anything that must actually be protected (starting
    or continuing a conversation, submitting contact/appointment/handoff
    data) additionally requires either an active installation status and
    passing origin/domain checks (abuse reduction, not authorization) or a
    `WidgetVisitorSession` capability token (real authorization) — see
    docs/security.md's "Public widget threat model".
    """

    __tablename__ = "widget_installations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "receptionist_id"],
            ["receptionists.tenant_id", "receptionists.id"],
            ondelete="CASCADE",
            name="fk_widget_installations_tenant_receptionist",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    receptionist_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    public_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, default=generate_public_id)

    status: Mapped[WidgetInstallationStatus] = mapped_column(
        SAEnum(
            WidgetInstallationStatus,
            name="widget_installation_status",
            native_enum=True,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        default=WidgetInstallationStatus.DRAFT,
    )

    # Normalized hostnames only (see app/core/domain_validation.py) — never
    # raw URLs, schemes, or paths. `[]` (the default) means no domain has
    # been approved yet; a DRAFT/newly-created installation cannot serve
    # any real request until at least one domain is added (or, in
    # development, "localhost" explicitly).
    allowed_domains: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    theme: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    launcher_position: Mapped[str] = mapped_column(String(20), nullable=False, default="bottom-right")

    privacy_notice: Mapped[str] = mapped_column(String(4000), nullable=False, default="")
    ai_disclosure: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        default=(
            "You are chatting with an automated assistant (currently running in "
            "zero-cost demonstration mode, not a live external AI model). "
            "A team member may follow up using the details you provide."
        ),
    )

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"WidgetInstallation(id={self.id!r}, public_id={self.public_id!r}, status={self.status!r})"

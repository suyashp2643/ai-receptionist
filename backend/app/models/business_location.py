import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BusinessLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_locations"
    __table_args__ = (
        # DB-level backstop for "at most one primary location per tenant" —
        # the service layer also unsets any other primary before setting a
        # new one, but this index makes the invariant unbreakable even under
        # a race between two concurrent requests.
        Index(
            "uq_business_locations_one_primary_per_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address_line: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    public_phone: Mapped[str | None] = mapped_column(String(20))
    working_hours: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"BusinessLocation(id={self.id!r}, tenant_id={self.tenant_id!r}, name={self.name!r})"

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import TenantMemberRole, TenantMemberStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TenantMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Links a User to a Tenant with a role. The sole source of truth for
    tenant access — role must always be read from here, never trusted from
    a client-supplied value.
    """

    __tablename__ = "tenant_members"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_members_tenant_user"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[TenantMemberRole] = mapped_column(
        SAEnum(
            TenantMemberRole,
            name="tenant_member_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[TenantMemberStatus] = mapped_column(
        SAEnum(
            TenantMemberStatus,
            name="tenant_member_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TenantMemberStatus.ACTIVE,
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"TenantMember(tenant_id={self.tenant_id!r}, user_id={self.user_id!r}, " f"role={self.role!r})"

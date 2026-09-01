import uuid

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ReceptionistWorkflow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned. One row per receptionist for the MVP (enforced by the
    unique constraint on receptionist_id) — `version` increments on
    structural change but this is not a history table in Phase 3."""

    __tablename__ = "receptionist_workflows"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receptionist_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("receptionists.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    qualification_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    qualification_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    enabled_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    safety_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    workflow_stages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def __repr__(self) -> str:
        return f"ReceptionistWorkflow(receptionist_id={self.receptionist_id!r}, version={self.version!r})"

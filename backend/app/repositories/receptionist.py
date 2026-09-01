import uuid

from sqlalchemy import select

from app.models.receptionist import Receptionist
from app.models.receptionist_workflow import ReceptionistWorkflow
from app.repositories.base import TenantScopedRepository


class ReceptionistRepository(TenantScopedRepository[Receptionist]):  # type: ignore[type-var]
    model = Receptionist

    def list_ordered(self) -> list[Receptionist]:
        stmt = select(Receptionist).where(Receptionist.tenant_id == self.tenant_id).order_by(Receptionist.created_at)
        return list(self.db.scalars(stmt).all())


class ReceptionistWorkflowRepository(TenantScopedRepository[ReceptionistWorkflow]):  # type: ignore[type-var]
    model = ReceptionistWorkflow

    def get_by_receptionist_id(self, receptionist_id: uuid.UUID) -> ReceptionistWorkflow | None:
        stmt = select(ReceptionistWorkflow).where(
            ReceptionistWorkflow.tenant_id == self.tenant_id,
            ReceptionistWorkflow.receptionist_id == receptionist_id,
        )
        return self.db.scalars(stmt).first()

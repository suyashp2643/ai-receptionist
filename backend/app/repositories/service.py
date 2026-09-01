from sqlalchemy import select

from app.models.service import Service
from app.repositories.base import TenantScopedRepository


class ServiceRepository(TenantScopedRepository[Service]):  # type: ignore[type-var]
    model = Service

    def list_ordered(self) -> list[Service]:
        stmt = (
            select(Service)
            .where(Service.tenant_id == self.tenant_id)
            .order_by(Service.display_order, Service.created_at)
        )
        return list(self.db.scalars(stmt).all())

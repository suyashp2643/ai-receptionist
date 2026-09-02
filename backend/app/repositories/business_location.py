import uuid

from sqlalchemy import select

from app.models.business_location import BusinessLocation
from app.repositories.base import TenantScopedRepository


class BusinessLocationRepository(TenantScopedRepository[BusinessLocation]):  # type: ignore[type-var]
    model = BusinessLocation

    def get_primary(self) -> BusinessLocation | None:
        stmt = select(BusinessLocation).where(
            BusinessLocation.tenant_id == self.tenant_id, BusinessLocation.is_primary.is_(True)
        )
        return self.db.scalars(stmt).first()

    def list_ordered(self) -> list[BusinessLocation]:
        stmt = (
            select(BusinessLocation)
            .where(BusinessLocation.tenant_id == self.tenant_id)
            .order_by(BusinessLocation.created_at)
        )
        return list(self.db.scalars(stmt).all())

    def list_active_ordered(self) -> list[BusinessLocation]:
        stmt = (
            select(BusinessLocation)
            .where(BusinessLocation.tenant_id == self.tenant_id, BusinessLocation.is_active.is_(True))
            .order_by(BusinessLocation.created_at)
        )
        return list(self.db.scalars(stmt).all())

    def get_active(self, location_id: uuid.UUID) -> BusinessLocation | None:
        location = self.get(location_id)
        if location is None or not location.is_active:
            return None
        return location

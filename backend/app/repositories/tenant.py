import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant


class TenantRepository:
    """Plain (non-tenant-scoped) repository — Tenant is the scoping root itself."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        return self.db.get(Tenant, tenant_id)

    def get_by_slug(self, slug: str) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.slug == slug)
        return self.db.scalars(stmt).first()

    def add(self, tenant: Tenant) -> Tenant:
        self.db.add(tenant)
        return tenant

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_profile import BusinessProfile


class BusinessProfileRepository:
    """1:1 with Tenant — looked up by tenant_id directly rather than through
    TenantScopedRepository's id-based `get`, since there's no separate
    resource id in the API surface for this."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_tenant_id(self, tenant_id: uuid.UUID) -> BusinessProfile | None:
        stmt = select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
        return self.db.scalars(stmt).first()

    def add(self, profile: BusinessProfile) -> BusinessProfile:
        self.db.add(profile)
        return profile

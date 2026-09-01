import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.repositories.base import TenantScopedRepository


class TenantMemberRepository:
    """Plain repository for membership lookups that ESTABLISH trust.

    These queries run before a tenant_id can be considered trusted (that's
    exactly what they're used to determine) — see app/api/deps.py — so they
    intentionally do not go through TenantScopedRepository.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_membership(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> TenantMember | None:
        stmt = select(TenantMember).where(TenantMember.tenant_id == tenant_id, TenantMember.user_id == user_id)
        return self.db.scalars(stmt).first()

    def list_for_user(self, user_id: uuid.UUID) -> list[TenantMember]:
        stmt = select(TenantMember).where(TenantMember.user_id == user_id)
        return list(self.db.scalars(stmt).all())

    def list_with_tenant_for_user(self, user_id: uuid.UUID) -> list[tuple[TenantMember, Tenant]]:
        stmt = (
            select(TenantMember, Tenant)
            .join(Tenant, Tenant.id == TenantMember.tenant_id)
            .where(TenantMember.user_id == user_id)
        )
        return [(m, t) for m, t in self.db.execute(stmt).all()]

    def add(self, member: TenantMember) -> TenantMember:
        self.db.add(member)
        return member


class TenantMemberScopedRepository(TenantScopedRepository[TenantMember]):  # type: ignore[type-var]
    """Used once a tenant_id is already trusted (post tenant-context resolution)
    — e.g. listing a tenant's members. See TenantScopedRepository for the
    tenant-filtering guarantee this provides.

    (mypy can't verify TenantMember structurally satisfies HasTenantAndId
    through its Mapped[...] descriptors — correct at runtime; see
    app/repositories/base.py.)
    """

    model = TenantMember

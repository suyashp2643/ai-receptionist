import uuid

from app.core.normalization import normalize_email
from app.core.security import hash_password
from app.models.enums import TenantMemberRole, TenantMemberStatus
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.models.user import User
from sqlalchemy.orm import Session


def make_user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "correct horse battery staple",
    display_name: str = "Test User",
) -> User:
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        normalized_email=normalize_email(email),
        password_hash=hash_password(password),
        display_name=display_name,
    )
    db.add(user)
    db.flush()
    return user


def make_tenant(db: Session, *, name: str = "Test Tenant") -> Tenant:
    tenant = Tenant(
        name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}", timezone="UTC"
    )
    db.add(tenant)
    db.flush()
    return tenant


def add_member(
    db: Session, *, tenant: Tenant, user: User, role: TenantMemberRole = TenantMemberRole.MEMBER
) -> TenantMember:
    member = TenantMember(
        tenant_id=tenant.id, user_id=user.id, role=role, status=TenantMemberStatus.ACTIVE
    )
    db.add(member)
    db.flush()
    return member


def make_tenant_with_owner(
    db: Session,
    *,
    tenant_name: str = "Test Tenant",
    owner_email: str | None = None,
    owner_password: str = "correct horse battery staple",
) -> tuple[Tenant, User, TenantMember]:
    user = make_user(db, email=owner_email, password=owner_password)
    tenant = make_tenant(db, name=tenant_name)
    member = add_member(db, tenant=tenant, user=user, role=TenantMemberRole.OWNER)
    return tenant, user, member

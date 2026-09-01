from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import (
    TenantContext,
    get_current_user,
    get_db,
    get_tenant_context,
    require_tenant_role,
)
from app.models.enums import TenantMemberRole
from app.models.user import User
from app.repositories.tenant import TenantRepository
from app.repositories.tenant_member import TenantMemberRepository, TenantMemberScopedRepository
from app.repositories.user import UserRepository
from app.schemas.tenant import (
    TenantCreate,
    TenantMemberRead,
    TenantMembershipSummary,
    TenantRead,
    TenantUpdate,
)
from app.services.tenant_service import create_tenant_with_owner

router = APIRouter()


@router.post("/tenants", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantRead:
    tenant, member = create_tenant_with_owner(db, user_id=current_user.id, name=payload.name, timezone=payload.timezone)
    return TenantRead(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        timezone=tenant.timezone,
        status=tenant.status,
        created_at=tenant.created_at,
        my_role=member.role,
    )


@router.get("/tenants", response_model=list[TenantMembershipSummary])
def list_my_tenants(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[TenantMembershipSummary]:
    rows = TenantMemberRepository(db).list_with_tenant_for_user(current_user.id)
    return [
        TenantMembershipSummary(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            role=member.role,
            status=member.status,
        )
        for member, tenant in rows
    ]


@router.get("/tenants/{tenant_id}", response_model=TenantRead)
def get_tenant(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> TenantRead:
    # ctx.tenant_id is trusted here: get_tenant_context already confirmed an
    # active membership row exists for exactly this tenant_id + current user,
    # and tenant_members.tenant_id is a FK to tenants.id, so this can't be None.
    tenant = TenantRepository(db).get_by_id(ctx.tenant_id)
    assert tenant is not None
    return TenantRead(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        timezone=tenant.timezone,
        status=tenant.status,
        created_at=tenant.created_at,
        my_role=ctx.role,
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantRead)
def update_tenant(
    payload: TenantUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> TenantRead:
    tenant = TenantRepository(db).get_by_id(ctx.tenant_id)
    assert tenant is not None  # same FK-backed invariant as get_tenant above
    if payload.name is not None:
        tenant.name = payload.name
    if payload.timezone is not None:
        tenant.timezone = payload.timezone

    return TenantRead(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        timezone=tenant.timezone,
        status=tenant.status,
        created_at=tenant.created_at,
        my_role=ctx.role,
    )


@router.get("/tenants/{tenant_id}/members", response_model=list[TenantMemberRead])
def list_tenant_members(
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> list[TenantMemberRead]:
    members = TenantMemberScopedRepository(db, ctx.tenant_id).list()
    user_repo = UserRepository(db)
    result: list[TenantMemberRead] = []
    for member in members:
        user = user_repo.get_by_id(member.user_id)
        assert user is not None  # tenant_members.user_id is a FK to users.id
        result.append(
            TenantMemberRead(
                id=member.id,
                user_id=member.user_id,
                display_name=user.display_name,
                normalized_email=user.normalized_email,
                role=member.role,
                status=member.status,
                created_at=member.created_at,
            )
        )
    return result

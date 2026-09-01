import uuid
from collections.abc import Generator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.db.session import get_db as _get_db
from app.models.enums import ROLE_RANK, TenantMemberRole, TenantMemberStatus
from app.models.user import User
from app.repositories.tenant_member import TenantMemberRepository
from app.repositories.user import UserRepository


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    token: str = Depends(get_bearer_token),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    try:
        payload = decode_access_token(settings=settings, token=token)
    except InvalidAccessTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token"
        ) from exc

    user = UserRepository(db).get_by_id(payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token"
        )
    return user


@dataclass(frozen=True)
class TenantContext:
    """Resolved, trusted membership for the {tenant_id} in the current request's
    URL path. role is always read fresh from the database here — it is never
    accepted from a request body, query param, or JWT claim."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: TenantMemberRole


def get_tenant_context(
    tenant_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    member = TenantMemberRepository(db).get_membership(tenant_id=tenant_id, user_id=current_user.id)
    # No membership at all -> 404, not 403: a non-member should not be able to
    # distinguish "tenant exists but you can't see it" from "tenant doesn't exist".
    if member is None or member.status != TenantMemberStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantContext(tenant_id=tenant_id, user_id=current_user.id, role=member.role)


def require_tenant_role(minimum: TenantMemberRole):
    """Centralized permission dependency factory — the only place role-rank
    comparisons happen. Route handlers must never re-implement this check."""

    def _dependency(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ROLE_RANK[ctx.role] < ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return ctx

    return _dependency

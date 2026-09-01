import re
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import TenantMemberRole, TenantMemberStatus
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.repositories.tenant import TenantRepository
from app.repositories.tenant_member import TenantMemberRepository

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_ATTEMPTS = 3


def slugify(name: str) -> str:
    base = _SLUG_INVALID_CHARS.sub("-", name.strip().lower()).strip("-")
    base = base[:180] or "workspace"
    # A random suffix is the actual collision defense; the DB unique
    # constraint on Tenant.slug is the real safety net either way.
    return f"{base}-{secrets.token_hex(3)}"


class TenantCreationError(Exception):
    pass


def create_tenant_with_owner(
    db: Session, *, user_id: uuid.UUID, name: str, timezone: str
) -> tuple[Tenant, TenantMember]:
    """Creates a tenant and the requesting user's owner membership.

    Uses a SAVEPOINT (db.begin_nested) so a vanishingly-rare slug collision
    can be retried with a fresh random suffix without discarding whatever
    else is pending in the outer request transaction (e.g. a just-created
    User row during registration) — that outer transaction still only
    commits once, at the end of the request (see app/db/session.get_db).
    """
    last_error: IntegrityError | None = None
    for _ in range(_MAX_SLUG_ATTEMPTS):
        try:
            with db.begin_nested():
                tenant = Tenant(name=name, slug=slugify(name), timezone=timezone)
                TenantRepository(db).add(tenant)
                db.flush()

                member = TenantMember(
                    tenant_id=tenant.id,
                    user_id=user_id,
                    role=TenantMemberRole.OWNER,
                    status=TenantMemberStatus.ACTIVE,
                    accepted_at=datetime.now(UTC),
                )
                TenantMemberRepository(db).add(member)
                db.flush()
            return tenant, member
        except IntegrityError as exc:
            last_error = exc
            continue

    raise TenantCreationError("Could not create a unique workspace slug.") from last_error

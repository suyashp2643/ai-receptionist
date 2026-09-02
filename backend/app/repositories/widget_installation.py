from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.widget_installation import WidgetInstallation
from app.repositories.base import TenantScopedRepository


class WidgetInstallationRepository(TenantScopedRepository[WidgetInstallation]):  # type: ignore[type-var]
    model = WidgetInstallation


def get_installation_by_public_id(db: Session, public_id: str) -> WidgetInstallation | None:
    """Deliberately a plain function, not a TenantScopedRepository method:
    the public widget API only ever has a `public_id`, not a tenant_id, so
    this lookup cannot be tenant-scoped — and constructing a
    TenantScopedRepository with a made-up tenant_id just to reach `self.db`
    would leave a half-valid repository object around that looks safe to
    reuse for a tenant-scoped call but silently isn't. Used only by
    app/api/widget_deps.py, which is the sole trusted place a request's
    real tenant_id is ever derived from — nothing downstream accepts a
    client-supplied tenant_id."""
    stmt = select(WidgetInstallation).where(WidgetInstallation.public_id == public_id)
    return db.scalars(stmt).first()

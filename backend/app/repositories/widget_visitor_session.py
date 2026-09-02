import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.widget_visitor_session import WidgetVisitorSession
from app.repositories.base import TenantScopedRepository


class WidgetVisitorSessionRepository(TenantScopedRepository[WidgetVisitorSession]):  # type: ignore[type-var]
    model = WidgetVisitorSession

    def get_by_conversation_id(self, conversation_id: uuid.UUID) -> WidgetVisitorSession | None:
        stmt = select(WidgetVisitorSession).where(
            WidgetVisitorSession.tenant_id == self.tenant_id,
            WidgetVisitorSession.conversation_id == conversation_id,
        )
        return self.db.scalars(stmt).first()


def get_session_by_token_hash(db: Session, token_hash: str) -> WidgetVisitorSession | None:
    """Mirrors app.repositories.widget_installation.get_installation_by_public_id:
    the presented capability token is the only thing the public API has
    before a tenant is known, so this lookup cannot be tenant-scoped.
    Callers must still verify installation/conversation scope and
    expiry/revocation before trusting the result (see
    app/services/widget_visitor_session_service.resolve_session_by_token)."""
    stmt = select(WidgetVisitorSession).where(WidgetVisitorSession.token_hash == token_hash)
    return db.scalars(stmt).first()

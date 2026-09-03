"""Single call site for writing an ActivityEvent — every dashboard action
that changes operational state (status changes, claims, note edits) must
route through `record()` rather than constructing the model directly, so
the set of action_type strings stays centralized and grep-able.

`metadata` must never contain a secret, token hash, password, full message
body, or transcript — only small, safe summary fields (e.g. an old/new
status pair). This is a convention enforced by code review, not a runtime
check, matching every other "never log/store this" rule in this codebase
(see e.g. WidgetVisitorSession's token_hash docstring)."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.activity_event import ActivityEvent
from app.repositories.activity_event import ActivityEventRepository


def record(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action_type: str,
    entity_type: str,
    entity_id: uuid.UUID,
    metadata: dict[str, Any] | None = None,
) -> ActivityEvent:
    event = ActivityEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        event_metadata=metadata or {},
    )
    ActivityEventRepository(db, tenant_id).add(event)
    db.flush()
    return event

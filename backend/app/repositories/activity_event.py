import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models.activity_event import ActivityEvent
from app.repositories.base import TenantScopedRepository


class ActivityEventRepository(TenantScopedRepository[ActivityEvent]):  # type: ignore[type-var]
    model = ActivityEvent

    def list_paginated(
        self,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[ActivityEvent], int]:
        conditions = [ActivityEvent.tenant_id == self.tenant_id]
        if entity_type is not None:
            conditions.append(ActivityEvent.entity_type == entity_type)
        if entity_id is not None:
            conditions.append(ActivityEvent.entity_id == entity_id)

        total = self.db.scalar(select(func.count()).select_from(ActivityEvent).where(*conditions)) or 0
        stmt = (
            select(ActivityEvent)
            .where(*conditions)
            .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all(), total

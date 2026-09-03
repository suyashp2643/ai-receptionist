"""Read-only, paginated activity/audit feed. Written only by application
services (app/services/activity_service.py) — there is no write route
here, and no public-widget code path ever touches this table."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context
from app.repositories.activity_event import ActivityEventRepository
from app.schemas.activity import ActivityEventRead, ActivityListResponse

router = APIRouter()

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


@router.get("/tenants/{tenant_id}/activity", response_model=ActivityListResponse)
def list_activity(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> ActivityListResponse:
    events, total = ActivityEventRepository(db, ctx.tenant_id).list_paginated(
        entity_type=entity_type, entity_id=entity_id, limit=limit, offset=offset
    )
    return ActivityListResponse(
        items=[ActivityEventRead.model_validate(e) for e in events], total=total, limit=limit, offset=offset
    )

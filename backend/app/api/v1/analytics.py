"""Tenant-scoped analytics overview and timeseries. Any active tenant
member may view — analytics contain aggregate counts, never raw PII."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context
from app.config import Settings, get_settings
from app.core.dashboard_dates import get_tenant_timezone
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    AnalyticsPreset,
    TimeseriesPoint,
    TimeseriesResponse,
)
from app.services import analytics_service
from app.services.analytics_service import InvalidAnalyticsRangeError

router = APIRouter()


def _resolve_period(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    preset: AnalyticsPreset,
    custom_start: date | None,
    custom_end: date | None,
    settings: Settings,
):
    tenant_timezone = get_tenant_timezone(db, tenant_id)
    try:
        return analytics_service.resolve_period(
            preset=preset,
            tenant_timezone=tenant_timezone,
            custom_start=custom_start,
            custom_end=custom_end,
            max_range_days=settings.analytics_max_range_days,
        ), tenant_timezone
    except InvalidAnalyticsRangeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/analytics/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    preset: AnalyticsPreset = Query(default="30d"),
    custom_start: date | None = None,
    custom_end: date | None = None,
    receptionist_id: uuid.UUID | None = None,
    include_test_preview: bool = False,
) -> AnalyticsOverviewResponse:
    period, _ = _resolve_period(
        db, ctx.tenant_id, preset=preset, custom_start=custom_start, custom_end=custom_end, settings=settings
    )
    overview = analytics_service.get_overview(
        db,
        tenant_id=ctx.tenant_id,
        period=period,
        receptionist_id=receptionist_id,
        include_test_preview=include_test_preview,
        settings=settings,
    )
    return AnalyticsOverviewResponse(**overview)


@router.get("/tenants/{tenant_id}/analytics/timeseries", response_model=TimeseriesResponse)
def get_analytics_timeseries(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    preset: AnalyticsPreset = Query(default="30d"),
    custom_start: date | None = None,
    custom_end: date | None = None,
    receptionist_id: uuid.UUID | None = None,
    include_test_preview: bool = False,
) -> TimeseriesResponse:
    period, tenant_timezone = _resolve_period(
        db, ctx.tenant_id, preset=preset, custom_start=custom_start, custom_end=custom_end, settings=settings
    )
    points = analytics_service.get_timeseries(
        db,
        tenant_id=ctx.tenant_id,
        period=period,
        tenant_timezone=tenant_timezone,
        receptionist_id=receptionist_id,
        include_test_preview=include_test_preview,
    )
    return TimeseriesResponse(points=[TimeseriesPoint(**p) for p in points])

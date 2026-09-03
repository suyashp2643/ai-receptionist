"""Shared "tenant timezone day range -> UTC datetime bounds" helper, used
by every dashboard list/export route that accepts a `date_from`/`date_to`
filter. A single definition so the same calendar day always converts to
the same UTC window regardless of which route computed it."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.tenant import TenantRepository


def get_tenant_timezone(db: Session, tenant_id: uuid.UUID) -> str:
    tenant = TenantRepository(db).get_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant.timezone


def day_bounds_utc(
    tenant_timezone: str, start: date | None, end: date | None
) -> tuple[datetime | None, datetime | None]:
    """`start`/`end` are inclusive calendar days in `tenant_timezone`;
    returns [start_utc, end_utc) — end_utc is the UTC instant of the start
    of the day *after* `end`, so callers use `< end_utc`, never `<=`."""
    if start is None and end is None:
        return None, None
    tz = ZoneInfo(tenant_timezone)
    start_utc = datetime.combine(start, time.min, tzinfo=tz).astimezone(UTC) if start else None
    end_utc = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC) if end else None
    return start_utc, end_utc

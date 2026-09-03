"""Owner/admin-only, tenant-scoped, date-range-bounded CSV exports. Every
export is generated entirely in memory (app/core/csv_export.py) — never
written to a file on the server — and recorded as an ActivityEvent. See
app/services/export_service.py for the exact columns each entity exports
(conversations are metadata-only: no transcript content) and for which
optional filters each entity accepts."""

import uuid
from collections.abc import Callable
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, require_tenant_role
from app.core.csv_export import ExportTooLargeError
from app.core.dashboard_dates import day_bounds_utc, get_tenant_timezone
from app.models.enums import TenantMemberRole
from app.services import activity_service, export_service
from app.services.export_service import InvalidExportFilterError

router = APIRouter()

ExportEntity = Literal["conversations", "contacts", "enquiries", "appointments", "handoffs"]

# Which optional filter kwarg (if any) each exporter accepts, and which
# query param feeds it — used only to decide what to pass through below;
# the actual validation/parsing lives in export_service.py.
_FILTER_KWARG_BY_ENTITY = {
    "conversations": "sources",
    "contacts": None,
    "enquiries": "statuses",
    "appointments": "statuses",
    "handoffs": "statuses",
}

# Explicitly typed `Callable[..., str]` — the five functions have
# genuinely different keyword-only filter parameters (`sources` vs
# `statuses` vs neither), so a precise Callable signature can't unify
# them; `...` is deliberate here, not a shortcut, since every call site
# below passes tenant_id/created_after/created_before positionally-by-
# keyword plus entity-specific **extra_kwargs looked up from
# _FILTER_KWARG_BY_ENTITY.
_EXPORTERS: dict[str, Callable[..., str]] = {
    "conversations": export_service.export_conversations_csv,
    "contacts": export_service.export_contacts_csv,
    "enquiries": export_service.export_enquiries_csv,
    "appointments": export_service.export_appointments_csv,
    "handoffs": export_service.export_handoffs_csv,
}


@router.get("/tenants/{tenant_id}/exports/{entity}")
def export_entity_csv(
    entity: ExportEntity,
    date_from: date = Query(...),
    date_to: date = Query(...),
    status_filter: list[str] | None = Query(default=None, alias="status"),
    source: list[str] | None = Query(default=None),
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    if entity not in _EXPORTERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown export entity.")
    if date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date_to cannot be before date_from."
        )
    if (date_to - date_from).days > 366:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Export range cannot exceed 366 days."
        )

    extra_kwargs = {}
    filter_kwarg = _FILTER_KWARG_BY_ENTITY[entity]
    if filter_kwarg == "sources" and source:
        extra_kwargs["sources"] = source
    elif filter_kwarg == "statuses" and status_filter:
        extra_kwargs["statuses"] = status_filter

    # Appointments are filtered by their own `requested_date` — exactly
    # what the appointments list page's date-range filter means (see
    # app/api/v1/dashboard_records.py::list_appointments) — never
    # `created_at`, unlike every other entity here. Keeping this
    # consistent is why an export always matches what the list page
    # showed when the filters look the same.
    if entity == "appointments":
        date_kwargs = {"requested_date_after": date_from, "requested_date_before": date_to}
    else:
        tenant_timezone = get_tenant_timezone(db, ctx.tenant_id)
        created_after, created_before = day_bounds_utc(tenant_timezone, date_from, date_to)
        assert created_after is not None and created_before is not None
        date_kwargs = {"created_after": created_after, "created_before": created_before}

    try:
        csv_text = _EXPORTERS[entity](db, tenant_id=ctx.tenant_id, **date_kwargs, **extra_kwargs)
    except ExportTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except InvalidExportFilterError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    activity_service.record(
        db,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action_type="export.downloaded",
        entity_type="export",
        # No single row is "the" export — entity_id is a synthetic id for
        # this export instance itself, not a reference to another table.
        entity_id=uuid.uuid4(),
        metadata={
            "entity": entity,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            **({"status": status_filter} if status_filter else {}),
            **({"source": source} if source else {}),
        },
    )
    db.commit()

    filename = f"{entity}_{date_from.isoformat()}_{date_to.isoformat()}.csv"
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

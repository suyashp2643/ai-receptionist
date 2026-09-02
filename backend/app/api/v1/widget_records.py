from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context
from app.repositories.appointment_request import AppointmentRequestRepository
from app.repositories.contact import ContactRepository
from app.repositories.enquiry import EnquiryRepository
from app.repositories.human_handoff import HumanHandoffRepository
from app.schemas.widget_records import (
    AppointmentRequestRead,
    ContactRead,
    EnquiryRead,
    HumanHandoffRead,
)

router = APIRouter()

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def _pagination(
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT), offset: int = Query(default=0, ge=0)
) -> tuple[int, int]:
    return limit, offset


@router.get("/tenants/{tenant_id}/widget-records/contacts", response_model=list[ContactRead])
def list_widget_contacts(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    pagination: tuple[int, int] = Depends(_pagination),
) -> list[ContactRead]:
    limit, offset = pagination
    contacts = ContactRepository(db, ctx.tenant_id).list_recent(limit=limit, offset=offset)
    return [ContactRead.model_validate(c) for c in contacts]


@router.get("/tenants/{tenant_id}/widget-records/enquiries", response_model=list[EnquiryRead])
def list_widget_enquiries(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    pagination: tuple[int, int] = Depends(_pagination),
) -> list[EnquiryRead]:
    limit, offset = pagination
    enquiries = EnquiryRepository(db, ctx.tenant_id).list_recent(limit=limit, offset=offset)
    return [EnquiryRead.model_validate(e) for e in enquiries]


@router.get("/tenants/{tenant_id}/widget-records/appointment-requests", response_model=list[AppointmentRequestRead])
def list_widget_appointment_requests(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    pagination: tuple[int, int] = Depends(_pagination),
) -> list[AppointmentRequestRead]:
    limit, offset = pagination
    requests_ = AppointmentRequestRepository(db, ctx.tenant_id).list_recent(limit=limit, offset=offset)
    return [AppointmentRequestRead.model_validate(r) for r in requests_]


@router.get("/tenants/{tenant_id}/widget-records/handoff-requests", response_model=list[HumanHandoffRead])
def list_widget_handoff_requests(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    pagination: tuple[int, int] = Depends(_pagination),
) -> list[HumanHandoffRead]:
    limit, offset = pagination
    handoffs = HumanHandoffRepository(db, ctx.tenant_id).list_recent(limit=limit, offset=offset)
    return [HumanHandoffRead.model_validate(h) for h in handoffs]

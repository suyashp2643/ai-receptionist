"""The operations dashboard's contact/enquiry/appointment/handoff list,
detail, and workflow-action routes. Distinct from
app/api/v1/widget_records.py (Phase 5's minimal read-only verification
views, kept as-is and unrelated to this module) — these add filtering,
sorting, search, pagination, and the actual status-change/claim actions.

Role policy (see docs/security.md's permission matrix):
- List/detail: any active tenant member.
- Enquiry status update, handoff claim/resolve: any active tenant member —
  day-to-day operational work.
- Appointment confirm/decline/cancel, handoff cancel: admin or owner only.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.core.dashboard_dates import day_bounds_utc, get_tenant_timezone
from app.models.enums import (
    AppointmentRequestStatus,
    EnquiryStatus,
    HandoffStatus,
    TenantMemberRole,
)
from app.repositories.appointment_request import AppointmentRequestFilters, AppointmentRequestRepository
from app.repositories.contact import ContactRepository
from app.repositories.enquiry import EnquiryFilters, EnquiryRepository
from app.repositories.human_handoff import HandoffFilters, HumanHandoffRepository
from app.schemas.dashboard_records import (
    AppointmentDetailResponse,
    AppointmentListItem,
    AppointmentListResponse,
    AppointmentStatusUpdateRequest,
    ContactDetailResponse,
    ContactListItem,
    ContactListResponse,
    EnquiryDetailResponse,
    EnquiryListItem,
    EnquiryListResponse,
    EnquiryStatusUpdateRequest,
    HandoffDetailResponse,
    HandoffListItem,
    HandoffListResponse,
    HandoffStatusUpdateRequest,
)
from app.services import appointment_request_service, enquiry_service, human_handoff_service
from app.services.appointment_request_service import InvalidAppointmentStatusTransitionError
from app.services.concurrency import VersionConflictError
from app.services.enquiry_service import InvalidEnquiryStatusTransitionError
from app.services.human_handoff_service import HandoffAlreadyClaimedError, InvalidHandoffStatusTransitionError

router = APIRouter()

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


# --- Contacts ----------------------------------------------------------


@router.get("/tenants/{tenant_id}/contacts", response_model=ContactListResponse)
def list_contacts(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=200),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> ContactListResponse:
    tz = get_tenant_timezone(db, ctx.tenant_id)
    created_after, created_before = day_bounds_utc(tz, date_from, date_to)
    rows, total = ContactRepository(db, ctx.tenant_id).list_dashboard(
        created_after=created_after,
        created_before=created_before,
        search=search,
        sort_descending=(sort_direction == "desc"),
        limit=limit,
        offset=offset,
    )
    return ContactListResponse(
        items=[ContactListItem.model_validate(c) for c in rows], total=total, limit=limit, offset=offset
    )


@router.get("/tenants/{tenant_id}/contacts/{contact_id}", response_model=ContactDetailResponse)
def get_contact_detail(
    contact_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> ContactDetailResponse:
    contact = ContactRepository(db, ctx.tenant_id).get(contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    enquiries = EnquiryRepository(db, ctx.tenant_id).list_by_contact_id(contact.id)
    appointments = AppointmentRequestRepository(db, ctx.tenant_id).list_by_contact_id(contact.id)
    handoffs = HumanHandoffRepository(db, ctx.tenant_id).list_by_contact_id(contact.id)

    return ContactDetailResponse(
        id=contact.id,
        name=contact.name,
        normalized_email=contact.normalized_email,
        normalized_phone=contact.normalized_phone,
        preferred_contact_method=contact.preferred_contact_method,
        marketing_consent=contact.marketing_consent,
        consent_captured_at=contact.consent_captured_at,
        source=contact.source,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        conversation_ids=[contact.conversation_id] if contact.conversation_id else [],
        enquiry_ids=[e.id for e in enquiries],
        appointment_request_ids=[a.id for a in appointments],
        handoff_ids=[h.id for h in handoffs],
    )


# --- Enquiries -----------------------------------------------------------


@router.get("/tenants/{tenant_id}/enquiries", response_model=EnquiryListResponse)
def list_enquiries(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    receptionist_id: uuid.UUID | None = None,
    status_filter: list[EnquiryStatus] | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=200),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> EnquiryListResponse:
    tz = get_tenant_timezone(db, ctx.tenant_id)
    created_after, created_before = day_bounds_utc(tz, date_from, date_to)
    rows, total = EnquiryRepository(db, ctx.tenant_id).list_dashboard(
        filters=EnquiryFilters(
            receptionist_id=receptionist_id,
            statuses=tuple(status_filter) if status_filter else None,
            created_after=created_after,
            created_before=created_before,
            search=search,
        ),
        sort_column="created_at",
        sort_descending=(sort_direction == "desc"),
        limit=limit,
        offset=offset,
    )
    return EnquiryListResponse(
        items=[EnquiryListItem.model_validate(e) for e in rows], total=total, limit=limit, offset=offset
    )


@router.get("/tenants/{tenant_id}/enquiries/{enquiry_id}", response_model=EnquiryDetailResponse)
def get_enquiry_detail(
    enquiry_id: uuid.UUID, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> EnquiryDetailResponse:
    enquiry = EnquiryRepository(db, ctx.tenant_id).get(enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found")
    return EnquiryDetailResponse.model_validate(enquiry)


@router.patch("/tenants/{tenant_id}/enquiries/{enquiry_id}/status", response_model=EnquiryDetailResponse)
def update_enquiry_status(
    enquiry_id: uuid.UUID,
    payload: EnquiryStatusUpdateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> EnquiryDetailResponse:
    enquiry = EnquiryRepository(db, ctx.tenant_id).get(enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found")
    try:
        enquiry_service.update_status(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            enquiry=enquiry,
            new_status=payload.status,
            expected_version=payload.expected_version,
        )
    except InvalidEnquiryStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return EnquiryDetailResponse.model_validate(enquiry)


# --- Appointments ----------------------------------------------------------


@router.get("/tenants/{tenant_id}/appointments", response_model=AppointmentListResponse)
def list_appointments(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    receptionist_id: uuid.UUID | None = None,
    status_filter: list[AppointmentRequestStatus] | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=200),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> AppointmentListResponse:
    rows, total = AppointmentRequestRepository(db, ctx.tenant_id).list_dashboard(
        filters=AppointmentRequestFilters(
            receptionist_id=receptionist_id,
            statuses=tuple(status_filter) if status_filter else None,
            requested_date_after=date_from,
            requested_date_before=date_to,
            search=search,
        ),
        sort_column="requested_date",
        sort_descending=(sort_direction == "desc"),
        limit=limit,
        offset=offset,
    )
    return AppointmentListResponse(
        items=[AppointmentListItem.model_validate(a) for a in rows], total=total, limit=limit, offset=offset
    )


@router.get("/tenants/{tenant_id}/appointments/{appointment_id}", response_model=AppointmentDetailResponse)
def get_appointment_detail(
    appointment_id: uuid.UUID, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> AppointmentDetailResponse:
    appointment = AppointmentRequestRepository(db, ctx.tenant_id).get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment request not found")
    return AppointmentDetailResponse.model_validate(appointment)


@router.patch("/tenants/{tenant_id}/appointments/{appointment_id}/status", response_model=AppointmentDetailResponse)
def update_appointment_status(
    appointment_id: uuid.UUID,
    payload: AppointmentStatusUpdateRequest,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> AppointmentDetailResponse:
    appointment = AppointmentRequestRepository(db, ctx.tenant_id).get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment request not found")
    try:
        appointment_request_service.update_status(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            appointment_request=appointment,
            new_status=payload.status,
            expected_version=payload.expected_version,
        )
    except InvalidAppointmentStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return AppointmentDetailResponse.model_validate(appointment)


# --- Handoffs ----------------------------------------------------------


def _is_clinic_emergency(db: Session, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
    from app.repositories.conversation import ConversationRepository

    conversation = ConversationRepository(db, tenant_id).get(conversation_id)
    return bool(conversation and conversation.had_clinic_emergency)


def _handoff_detail(db: Session, tenant_id: uuid.UUID, handoff) -> HandoffDetailResponse:  # noqa: ANN001
    return HandoffDetailResponse.model_validate(handoff).model_copy(
        update={"is_clinic_emergency": _is_clinic_emergency(db, tenant_id, handoff.conversation_id)}
    )


@router.get("/tenants/{tenant_id}/handoffs", response_model=HandoffListResponse)
def list_handoffs(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    receptionist_id: uuid.UUID | None = None,
    status_filter: list[HandoffStatus] | None = Query(default=None, alias="status"),
    urgency: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=200),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> HandoffListResponse:
    tz = get_tenant_timezone(db, ctx.tenant_id)
    created_after, created_before = day_bounds_utc(tz, date_from, date_to)
    rows, total = HumanHandoffRepository(db, ctx.tenant_id).list_dashboard(
        filters=HandoffFilters(
            receptionist_id=receptionist_id,
            statuses=tuple(status_filter) if status_filter else None,
            urgency=urgency,
            created_after=created_after,
            created_before=created_before,
            search=search,
        ),
        sort_column="created_at",
        sort_descending=(sort_direction == "desc"),
        limit=limit,
        offset=offset,
    )
    return HandoffListResponse(
        items=[HandoffListItem.model_validate(h) for h in rows], total=total, limit=limit, offset=offset
    )


@router.get("/tenants/{tenant_id}/handoffs/{handoff_id}", response_model=HandoffDetailResponse)
def get_handoff_detail(
    handoff_id: uuid.UUID, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> HandoffDetailResponse:
    handoff = HumanHandoffRepository(db, ctx.tenant_id).get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found")
    return _handoff_detail(db, ctx.tenant_id, handoff)


@router.post("/tenants/{tenant_id}/handoffs/{handoff_id}/claim", response_model=HandoffDetailResponse)
def claim_handoff(
    handoff_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> HandoffDetailResponse:
    """Phase 9 audit fix: every other action on this surface (get, update
    status) explicitly checks tenant scoping first and returns a clean 404
    for a handoff that doesn't belong to the caller's tenant — this route
    previously skipped that check and let `human_handoff_service.claim()`'s
    atomic UPDATE silently match zero rows for that case too, collapsing it
    into the same 409 used for "already claimed by a teammate". Not a
    cross-tenant data leak (the UPDATE's own WHERE clause was always
    tenant-scoped, so nothing could ever actually be claimed), but
    inconsistent with this codebase's stated convention that a non-existent
    or foreign-tenant resource ID gets 404, not a status conflated with a
    same-tenant business conflict."""
    handoff = HumanHandoffRepository(db, ctx.tenant_id).get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found")
    try:
        handoff = human_handoff_service.claim(
            db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, handoff_id=handoff_id
        )
    except HandoffAlreadyClaimedError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _handoff_detail(db, ctx.tenant_id, handoff)


@router.patch("/tenants/{tenant_id}/handoffs/{handoff_id}/status", response_model=HandoffDetailResponse)
def update_handoff_status(
    handoff_id: uuid.UUID,
    payload: HandoffStatusUpdateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> HandoffDetailResponse:
    handoff = HumanHandoffRepository(db, ctx.tenant_id).get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found")
    # Cancelling is an admin/owner override; resolving is normal member work.
    if payload.status == HandoffStatus.CANCELLED and ctx.role == TenantMemberRole.MEMBER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin or owner can cancel a handoff."
        )
    try:
        human_handoff_service.update_status(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            handoff=handoff,
            new_status=payload.status,
            expected_version=payload.expected_version,
        )
    except InvalidHandoffStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _handoff_detail(db, ctx.tenant_id, handoff)

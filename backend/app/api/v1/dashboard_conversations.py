"""The operations dashboard's conversation list/detail — every conversation
regardless of source (test, preview, or genuine widget), unlike
app/api/v1/conversations.py's `/test-conversations` routes which are
scoped to the private test console only. Minimum role is `member`: viewing
conversations is a normal day-to-day operational task, not a
configuration change.

Never exposes: the system prompt, provider API keys/secrets, capability
tokens or their hashes, or any other tenant's data — see
ConversationMessageRead's fields (reused unchanged from Phase 4)."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.api.v1.conversations import _get_conversation_or_404
from app.core.conversation_source import ConversationSource, classify
from app.core.dashboard_dates import day_bounds_utc, get_tenant_timezone
from app.models.enums import ConversationStatus, TenantMemberRole
from app.repositories.appointment_request import AppointmentRequestRepository
from app.repositories.contact import ContactRepository
from app.repositories.conversation import (
    ConversationFilters,
    ConversationMessageRepository,
    ConversationRepository,
    ConversationSummaryRepository,
)
from app.repositories.enquiry import EnquiryRepository
from app.repositories.human_handoff import HumanHandoffRepository
from app.repositories.widget_visitor_session import WidgetVisitorSessionRepository
from app.schemas.conversation import ConversationMessageRead, ConversationSummaryRead
from app.schemas.dashboard_conversations import (
    CONVERSATION_SORT_ALLOWLIST,
    ConversationDashboardDetailResponse,
    ConversationDetailAppointment,
    ConversationDetailContact,
    ConversationDetailEnquiry,
    ConversationDetailHandoff,
    ConversationDetailWidgetSession,
    ConversationListItem,
    ConversationListResponse,
    WidgetSessionRevokeResponse,
)
from app.services import activity_service, widget_visitor_session_service

router = APIRouter()

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25
MAX_MESSAGE_PAGE_SIZE = 500


def _parse_source_filter(sources: list[str] | None) -> tuple[ConversationSource, ...] | None:
    if not sources:
        return None
    try:
        return tuple(ConversationSource(s) for s in sources)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/conversations", response_model=ConversationListResponse)
def list_conversations(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    receptionist_id: uuid.UUID | None = None,
    source: list[str] | None = Query(default=None),
    status_filter: list[ConversationStatus] | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    only_safety_events: bool = False,
    qualification_complete: bool | None = None,
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="started_at"),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> ConversationListResponse:
    if sort not in CONVERSATION_SORT_ALLOWLIST:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Cannot sort by '{sort}'.")

    tenant_timezone = get_tenant_timezone(db, ctx.tenant_id)
    started_after, started_before = day_bounds_utc(tenant_timezone, date_from, date_to)

    filters = ConversationFilters(
        receptionist_id=receptionist_id,
        sources=_parse_source_filter(source),
        statuses=tuple(status_filter) if status_filter else None,
        started_after=started_after,
        started_before=started_before,
        only_safety_events=only_safety_events,
        qualification_complete=qualification_complete,
        search=search,
    )
    rows, total = ConversationRepository(db, ctx.tenant_id).list_dashboard(
        filters=filters,
        sort_column=sort,
        sort_descending=(sort_direction == "desc"),
        limit=limit,
        offset=offset,
    )

    items = [
        ConversationListItem(
            id=conv.id,
            receptionist_id=conv.receptionist_id,
            started_at=conv.started_at,
            last_message_at=conv.last_message_at,
            status=conv.status,
            source=source_value,
            visitor_reference=conv.visitor_reference,
            qualification_complete=conv.qualification_complete,
            had_safety_event=conv.had_safety_event,
            had_clinic_emergency=conv.had_clinic_emergency,
        )
        for conv, source_value in rows
    ]
    return ConversationListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/tenants/{tenant_id}/conversations/{conversation_id}", response_model=ConversationDashboardDetailResponse)
def get_conversation_detail(
    conversation_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    message_limit: int = Query(default=200, ge=1, le=MAX_MESSAGE_PAGE_SIZE),
    message_offset: int = Query(default=0, ge=0),
) -> ConversationDashboardDetailResponse:
    conversation = _get_conversation_or_404(conversation_id, ctx, db)

    messages, message_total = ConversationMessageRepository(db, ctx.tenant_id).list_for_conversation(
        conversation_id, limit=message_limit, offset=message_offset
    )
    summary = ConversationSummaryRepository(db, ctx.tenant_id).get_by_conversation_id(conversation_id)
    session = WidgetVisitorSessionRepository(db, ctx.tenant_id).get_by_conversation_id(conversation_id)
    contact = ContactRepository(db, ctx.tenant_id).get_by_conversation_id(conversation_id)
    enquiry = EnquiryRepository(db, ctx.tenant_id).get_by_conversation_id(conversation_id)
    appointments = AppointmentRequestRepository(db, ctx.tenant_id).list_by_conversation_id(conversation_id)
    handoffs = HumanHandoffRepository(db, ctx.tenant_id).list_by_conversation_id(conversation_id)

    return ConversationDashboardDetailResponse(
        id=conversation.id,
        receptionist_id=conversation.receptionist_id,
        source=classify(conversation.mode, session.is_platform_preview if session else None),
        status=conversation.status,
        provider=conversation.provider,
        locale=conversation.locale,
        started_at=conversation.started_at,
        last_message_at=conversation.last_message_at,
        completed_at=conversation.completed_at,
        qualification_complete=conversation.qualification_complete,
        collected_data=conversation.collected_data,
        had_safety_event=conversation.had_safety_event,
        had_clinic_emergency=conversation.had_clinic_emergency,
        messages=[ConversationMessageRead.model_validate(m) for m in messages],
        message_total=message_total,
        message_limit=message_limit,
        message_offset=message_offset,
        summary=ConversationSummaryRead.model_validate(summary) if summary else None,
        contact=ConversationDetailContact.model_validate(contact) if contact else None,
        enquiry=ConversationDetailEnquiry(id=enquiry.id, status=enquiry.status.value) if enquiry else None,
        appointment_requests=[
            ConversationDetailAppointment(id=a.id, status=a.status.value, requested_date=a.requested_date)
            for a in appointments
        ],
        handoffs=[ConversationDetailHandoff(id=h.id, status=h.status.value) for h in handoffs],
        widget_session=(
            ConversationDetailWidgetSession(
                id=session.id,
                is_revoked=session.revoked_at is not None,
                expires_at=session.expires_at,
            )
            if session
            else None
        ),
    )


@router.post(
    "/tenants/{tenant_id}/conversations/{conversation_id}/revoke-widget-session",
    response_model=WidgetSessionRevokeResponse,
)
def revoke_conversation_widget_session(
    conversation_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> WidgetSessionRevokeResponse:
    """Immediately invalidates the one visitor capability token scoped to
    this conversation, without touching the wider widget installation (see
    app/services/widget_visitor_session_service.revoke_session — previously
    unwired to any route; this closes that gap). Idempotent: revoking an
    already-revoked session is a harmless no-op, not an error, matching this
    codebase's convention of not treating a repeated safe action as a
    failure (e.g. handoff/appointment idempotency keys)."""
    conversation = _get_conversation_or_404(conversation_id, ctx, db)
    session = WidgetVisitorSessionRepository(db, ctx.tenant_id).get_by_conversation_id(conversation.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No widget visitor session exists for this conversation.",
        )
    if session.revoked_at is None:
        widget_visitor_session_service.revoke_session(session)
        activity_service.record(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action_type="widget_session.revoked",
            entity_type="conversation",
            entity_id=conversation.id,
            metadata={},
        )
    db.commit()
    assert session.revoked_at is not None
    return WidgetSessionRevokeResponse(status="revoked", revoked_at=session.revoked_at)

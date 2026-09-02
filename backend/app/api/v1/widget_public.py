"""The public embeddable-widget API. No dashboard JWT is ever required or
accepted here — every route resolves its tenant/receptionist server-side
from `public_id` (a WidgetInstallation's public, non-secret identifier) and,
where a specific conversation is touched, a visitor capability token (see
app/api/widget_deps.py). Reuses Phase 4's ConversationOrchestrator and SSE
adapter rather than duplicating them — `stream_sync_generator` is imported
and called as-is; `ConversationOrchestrator.start_conversation` gained two
optional, backward-compatible `mode`/`channel` keyword arguments (Phase 4's
defaults preserved exactly) so this module can request
`mode=ConversationMode.WIDGET, channel=ConversationChannel.WIDGET` — see
docs/architecture.md for the exact diff and confirmation that Phase 4's own
call site and test suite are unaffected.
"""

import json
import uuid
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai.errors import ConversationError
from app.ai.orchestrator import ConversationOrchestrator
from app.ai.providers.base import ProviderConfigurationError
from app.ai.providers.factory import get_provider
from app.api.deps import get_db, get_session_scope_factory
from app.api.v1.conversations import stream_sync_generator
from app.api.widget_deps import (
    WidgetVisitorContext,
    get_active_widget_installation,
    get_widget_installation,
    get_widget_visitor_context,
    get_widget_visitor_context_from_token,
    rate_limit,
    validate_widget_origin,
)
from app.config import Settings, get_settings
from app.models.enums import ConversationChannel, ConversationMessageRole, ConversationMode, ConversationStatus
from app.models.widget_installation import WidgetInstallation
from app.repositories.business_location import BusinessLocationRepository
from app.repositories.business_profile import BusinessProfileRepository
from app.repositories.contact import ContactRepository
from app.repositories.conversation import ConversationMessageRepository, ConversationRepository
from app.repositories.receptionist import ReceptionistRepository
from app.repositories.service import ServiceRepository
from app.schemas.conversation import SendMessageRequest, StartConversationRequest
from app.schemas.widget_public import (
    ContactFields,
    PublicLocationOption,
    PublicServiceOption,
    WidgetAppointmentRequestCreate,
    WidgetAppointmentRequestResponse,
    WidgetConfigRead,
    WidgetContactCreate,
    WidgetContactCreateResponse,
    WidgetConversationDetailResponse,
    WidgetConversationRead,
    WidgetHandoffRequestCreate,
    WidgetHandoffRequestResponse,
    WidgetMessageRead,
    WidgetSessionStartResponse,
)
from app.services import appointment_request_service, contact_service, enquiry_service, human_handoff_service
from app.services.appointment_request_service import InvalidAppointmentRequestError
from app.services.widget_visitor_session_service import issue_session

router = APIRouter(prefix="/widget/{public_id}")

_PUBLIC_MESSAGE_ROLES = (ConversationMessageRole.USER, ConversationMessageRole.ASSISTANT)


def _resolve_provider_or_500(settings: Settings):  # noqa: ANN201
    try:
        return get_provider(settings)
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI provider is not configured correctly."
        ) from exc


def _format_sse(event: dict) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"


def _resolve_contact_id(
    db: Session, *, ctx: WidgetVisitorContext, inline_contact: ContactFields | None
) -> uuid.UUID | None:
    """Shared by appointment-request and handoff-request creation: capture
    inline contact fields if given, otherwise fall back to whatever contact
    (if any) was already captured earlier in this same conversation."""
    if inline_contact is not None and (inline_contact.name or inline_contact.email or inline_contact.phone):
        contact = contact_service.capture_contact(
            db,
            tenant_id=ctx.tenant_id,
            conversation_id=ctx.session.conversation_id,
            name=inline_contact.name,
            email=inline_contact.email,
            phone=inline_contact.phone,
            preferred_contact_method=inline_contact.preferred_contact_method,
            marketing_consent=inline_contact.marketing_consent,
        )
        return contact.id
    existing = ContactRepository(db, ctx.tenant_id).get_by_conversation_id(ctx.session.conversation_id)
    return existing.id if existing is not None else None


@router.get("/config", response_model=WidgetConfigRead, dependencies=[Depends(validate_widget_origin)])
def get_widget_config(
    installation: WidgetInstallation = Depends(get_widget_installation),
    db: Session = Depends(get_db),
) -> WidgetConfigRead:
    receptionist = ReceptionistRepository(db, installation.tenant_id).get(installation.receptionist_id)
    if receptionist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found.")
    profile = BusinessProfileRepository(db).get_by_tenant_id(installation.tenant_id)

    business_name = profile.business_name if profile and profile.business_name else receptionist.name
    supported_languages = list(profile.supported_languages) if profile and profile.supported_languages else ["en"]

    services = ServiceRepository(db, installation.tenant_id).list_active_ordered()
    locations = BusinessLocationRepository(db, installation.tenant_id).list_active_ordered()

    return WidgetConfigRead(
        status=installation.status.value,
        business_name=business_name,
        receptionist_name=receptionist.name,
        welcome_message=receptionist.welcome_message,
        suggested_questions=list(receptionist.suggested_questions or []),
        logo_url=receptionist.logo_url,
        accent_color=receptionist.accent_color,
        supported_languages=supported_languages,
        voice_enabled=bool(installation.theme.get("voice_enabled", True)),
        theme=installation.theme,
        launcher_position=installation.launcher_position,
        ai_disclosure=installation.ai_disclosure,
        privacy_notice=installation.privacy_notice,
        mock_mode=True,
        business_public_email=profile.public_email if profile else None,
        business_public_phone=profile.public_phone if profile else None,
        services=[PublicServiceOption(id=s.id, name=s.name, description=s.description) for s in services],
        locations=[PublicLocationOption(id=loc.id, name=loc.name, timezone=loc.timezone) for loc in locations],
    )


def _start_conversation_and_session(
    db: Session, *, installation: WidgetInstallation, payload: StartConversationRequest, settings: Settings
) -> WidgetSessionStartResponse:
    provider = _resolve_provider_or_500(settings)
    orchestrator = ConversationOrchestrator(
        db,
        tenant_id=installation.tenant_id,
        provider=provider,
        retrieval_limit=settings.retrieval_result_limit,
        max_context_chars=settings.max_conversation_context_chars,
    )
    try:
        conversation = orchestrator.start_conversation(
            receptionist_id=installation.receptionist_id,
            visitor_reference=payload.visitor_reference,
            locale=payload.locale,
            mode=ConversationMode.WIDGET,
            channel=ConversationChannel.WIDGET,
        )
    except ConversationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    session, raw_token = issue_session(
        db,
        tenant_id=installation.tenant_id,
        widget_installation_id=installation.id,
        conversation_id=conversation.id,
        ttl_hours=settings.widget_visitor_session_ttl_hours,
    )
    db.commit()
    return WidgetSessionStartResponse(
        capability_token=raw_token,
        expires_at=session.expires_at,
        conversation=WidgetConversationRead.model_validate(conversation),
    )


@router.post(
    "/sessions",
    response_model=WidgetSessionStartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(validate_widget_origin),
        Depends(rate_limit("session_create", limit=20, window_seconds=3600)),
    ],
)
def create_widget_session(
    payload: StartConversationRequest,
    installation: WidgetInstallation = Depends(get_active_widget_installation),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WidgetSessionStartResponse:
    return _start_conversation_and_session(db, installation=installation, payload=payload, settings=settings)


@router.post(
    "/conversations",
    response_model=WidgetSessionStartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(validate_widget_origin),
        Depends(rate_limit("session_create", limit=20, window_seconds=3600)),
    ],
)
def create_widget_conversation(
    payload: StartConversationRequest,
    ctx: WidgetVisitorContext = Depends(get_widget_visitor_context_from_token),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WidgetSessionStartResponse:
    """Requires an existing, still-valid capability token from this same
    installation (proof the caller already completed the domain-gated
    /sessions handshake once) — this is the "start a new conversation"
    action from within an already-open widget, not a general-purpose
    unauthenticated conversation factory."""
    return _start_conversation_and_session(db, installation=ctx.installation, payload=payload, settings=settings)


@router.get(
    "/conversations/{conversation_id}",
    response_model=WidgetConversationDetailResponse,
)
def get_widget_conversation(
    ctx: WidgetVisitorContext = Depends(get_widget_visitor_context),
    db: Session = Depends(get_db),
) -> WidgetConversationDetailResponse:
    conversation = ConversationRepository(db, ctx.tenant_id).get(ctx.session.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    messages, _ = ConversationMessageRepository(db, ctx.tenant_id).list_for_conversation(
        conversation.id, limit=500, offset=0
    )
    public_messages = [m for m in messages if m.role in _PUBLIC_MESSAGE_ROLES]
    return WidgetConversationDetailResponse(
        conversation=WidgetConversationRead.model_validate(conversation),
        messages=[WidgetMessageRead.model_validate(m) for m in public_messages],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    dependencies=[Depends(rate_limit("message", limit=30, window_seconds=60))],
)
def send_widget_message(
    payload: SendMessageRequest,
    ctx: WidgetVisitorContext = Depends(get_widget_visitor_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    session_scope_factory: Callable[[], AbstractContextManager[Session]] = Depends(get_session_scope_factory),
) -> StreamingResponse:
    conversation = ConversationRepository(db, ctx.tenant_id).get(ctx.session.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    if conversation.status != ConversationStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This conversation is no longer active.")

    _, message_total = ConversationMessageRepository(db, ctx.tenant_id).list_for_conversation(
        conversation.id, limit=1, offset=0
    )
    if message_total >= settings.widget_max_messages_per_conversation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This conversation has reached its message limit."
        )

    provider = _resolve_provider_or_500(settings)
    tenant_id = ctx.tenant_id
    conversation_id = conversation.id

    def sync_event_stream() -> Generator[str, None, None]:
        with session_scope_factory() as stream_db:
            orchestrator = ConversationOrchestrator(
                stream_db,
                tenant_id=tenant_id,
                provider=provider,
                retrieval_limit=settings.retrieval_result_limit,
                max_context_chars=settings.max_conversation_context_chars,
                is_disconnected=lambda: False,
            )
            try:
                for event in orchestrator.submit_message(
                    conversation_id, content=payload.content, idempotency_key=payload.idempotency_key
                ):
                    yield _format_sse(event)
            except ConversationError as exc:
                code = getattr(exc, "code", "conversation_error")
                yield _format_sse({"event": "response.error", "data": {"code": code, "message": str(exc)}})
                return

            updated_conversation = ConversationRepository(stream_db, tenant_id).get(conversation_id)
            if updated_conversation is not None:
                existing_contact = ContactRepository(stream_db, tenant_id).get_by_conversation_id(conversation_id)
                enquiry_service.upsert_enquiry_from_conversation(
                    stream_db,
                    tenant_id=tenant_id,
                    conversation=updated_conversation,
                    contact_id=existing_contact.id if existing_contact else None,
                )

    return StreamingResponse(
        stream_sync_generator(sync_event_stream()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post(
    "/contacts",
    response_model=WidgetContactCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("contact", limit=10, window_seconds=3600))],
)
def create_widget_contact(
    payload: WidgetContactCreate,
    ctx: WidgetVisitorContext = Depends(get_widget_visitor_context_from_token),
    db: Session = Depends(get_db),
) -> WidgetContactCreateResponse:
    if not (payload.name or payload.email or payload.phone):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide at least a name, email, or phone number."
        )
    contact = contact_service.capture_contact(
        db,
        tenant_id=ctx.tenant_id,
        conversation_id=ctx.session.conversation_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        preferred_contact_method=payload.preferred_contact_method,
        marketing_consent=payload.marketing_consent,
    )
    db.commit()
    return WidgetContactCreateResponse(contact_id=contact.id, marketing_consent=contact.marketing_consent)


@router.post(
    "/appointment-requests",
    response_model=WidgetAppointmentRequestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("appointment_request", limit=5, window_seconds=3600))],
)
def create_widget_appointment_request(
    payload: WidgetAppointmentRequestCreate,
    ctx: WidgetVisitorContext = Depends(get_widget_visitor_context_from_token),
    db: Session = Depends(get_db),
) -> WidgetAppointmentRequestResponse:
    contact_id = _resolve_contact_id(db, ctx=ctx, inline_contact=payload.contact)
    try:
        appointment_request = appointment_request_service.create_appointment_request(
            db,
            tenant_id=ctx.tenant_id,
            receptionist_id=ctx.installation.receptionist_id,
            conversation_id=ctx.session.conversation_id,
            contact_id=contact_id,
            location_id=payload.location_id,
            service_id=payload.service_id,
            requested_date=payload.requested_date,
            requested_time=payload.requested_time,
            requested_time_window=payload.requested_time_window,
            timezone=payload.timezone,
            notes=payload.notes,
            idempotency_key=payload.idempotency_key,
        )
    except InvalidAppointmentRequestError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return WidgetAppointmentRequestResponse(
        reference=str(appointment_request.id),
        status=appointment_request.status,
        requested_date=appointment_request.requested_date,
        requested_time=appointment_request.requested_time,
        requested_time_window=appointment_request.requested_time_window,
        timezone=appointment_request.timezone,
    )


@router.post(
    "/handoff-requests",
    response_model=WidgetHandoffRequestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("handoff_request", limit=5, window_seconds=3600))],
)
def create_widget_handoff_request(
    payload: WidgetHandoffRequestCreate,
    ctx: WidgetVisitorContext = Depends(get_widget_visitor_context_from_token),
    db: Session = Depends(get_db),
) -> WidgetHandoffRequestResponse:
    contact_id = _resolve_contact_id(db, ctx=ctx, inline_contact=payload.contact)
    handoff = human_handoff_service.create_handoff_request(
        db,
        tenant_id=ctx.tenant_id,
        receptionist_id=ctx.installation.receptionist_id,
        conversation_id=ctx.session.conversation_id,
        contact_id=contact_id,
        reason=payload.reason,
        urgency=payload.urgency,
        preferred_contact_method=payload.contact.preferred_contact_method if payload.contact else None,
        idempotency_key=payload.idempotency_key,
    )
    db.commit()
    return WidgetHandoffRequestResponse(reference=str(handoff.id), status=handoff.status)

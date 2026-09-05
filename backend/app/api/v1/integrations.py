"""Dashboard-facing integration management API.

Role policy (see docs/security.md's Phase 8 section):
- List/detail/delivery-history: any active tenant member (read-only).
- Create/update/pause/resume/disable/rotate-secret/generate-inbound-key/
  verify/send-test-event/replay: owner or admin only.
- Non-member: 404 (see app.api.deps.get_tenant_context). Unauthenticated: 401.

No route here ever returns a signing secret or a raw inbound API key
except the one response immediately after generate_inbound_api_key —
see IntegrationConnectionRead/InboundApiKeyCreatedResponse in
app/schemas/integration.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.config import Settings, get_settings
from app.core.crypto import SecretDecryptionError
from app.integrations.field_mapping import FieldMappingError, preview_field_mapping
from app.models.enums import IntegrationConnectorType, TenantMemberRole
from app.repositories.integration import IntegrationOutboxEventRepository
from app.schemas.integration import (
    FieldMappingPreviewRequest,
    FieldMappingPreviewResponse,
    InboundApiKeyCreatedResponse,
    IntegrationConnectionCreate,
    IntegrationConnectionListResponse,
    IntegrationConnectionRead,
    IntegrationConnectionUpdate,
    IntegrationDeliveryListResponse,
    IntegrationOutboxEventRead,
    IntegrationSecretRotateRequest,
    IntegrationVerifyResponse,
    IntegrationVersionedActionRequest,
    ProcessPendingNowResponse,
    TenantIntegrationHealthRead,
)
from app.services import integration_connection_service
from app.services.concurrency import VersionConflictError
from app.services.integration_connection_service import IntegrationConfigError
from app.services.integration_health_service import (
    DEFAULT_WINDOW_HOURS,
    MAX_WINDOW_HOURS,
    get_tenant_integration_health,
)

router = APIRouter()

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


def _connector_type_or_422(raw: str) -> IntegrationConnectorType:
    try:
        return IntegrationConnectorType(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"'{raw}' is not a recognized connector type."
        ) from exc


def _get_connection_or_404(db: Session, ctx: TenantContext, connection_id: uuid.UUID):  # noqa: ANN201
    connection = integration_connection_service.get_connection(db, ctx.tenant_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration connection not found")
    return connection


@router.get("/tenants/{tenant_id}/integrations", response_model=IntegrationConnectionListResponse)
def list_integration_connections(
    ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> IntegrationConnectionListResponse:
    connections = integration_connection_service.list_connections(db, ctx.tenant_id)
    return IntegrationConnectionListResponse(items=[IntegrationConnectionRead.from_model(c) for c in connections])


@router.post(
    "/tenants/{tenant_id}/integrations",
    response_model=IntegrationConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_integration_connection(
    payload: IntegrationConnectionCreate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IntegrationConnectionRead:
    connector_type = _connector_type_or_422(payload.connector_type)
    try:
        connection = integration_connection_service.create_connection(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            connector_type=connector_type,
            name=payload.name,
            config=payload.config,
            enabled_event_types=payload.enabled_event_types,
            signing_secret=payload.signing_secret,
            settings=settings,
        )
    except IntegrationConfigError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return IntegrationConnectionRead.from_model(connection)


@router.get("/tenants/{tenant_id}/integrations/health", response_model=TenantIntegrationHealthRead)
def get_tenant_integrations_health(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    window_hours: int = Query(default=DEFAULT_WINDOW_HOURS, ge=1, le=MAX_WINDOW_HOURS),
) -> TenantIntegrationHealthRead:
    """Registered BEFORE the /{connection_id} route below so "health" is
    never mistaken for a connection id — FastAPI/Starlette matches routes
    in registration order, and a literal path segment must be registered
    ahead of a same-shaped parameterized one to win the match."""
    health = get_tenant_integration_health(db, tenant_id=ctx.tenant_id, settings=settings, window_hours=window_hours)
    return TenantIntegrationHealthRead.from_health(health)


@router.get("/tenants/{tenant_id}/integrations/{connection_id}", response_model=IntegrationConnectionRead)
def get_integration_connection(
    connection_id: uuid.UUID, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> IntegrationConnectionRead:
    connection = _get_connection_or_404(db, ctx, connection_id)
    return IntegrationConnectionRead.from_model(connection)


@router.put("/tenants/{tenant_id}/integrations/{connection_id}", response_model=IntegrationConnectionRead)
def update_integration_connection(
    connection_id: uuid.UUID,
    payload: IntegrationConnectionUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IntegrationConnectionRead:
    connection = _get_connection_or_404(db, ctx, connection_id)
    try:
        integration_connection_service.update_config_and_events(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            connection=connection,
            config=payload.config,
            enabled_event_types=payload.enabled_event_types,
            expected_version=payload.expected_version,
            settings=settings,
        )
    except IntegrationConfigError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return IntegrationConnectionRead.from_model(connection)


@router.post(
    "/tenants/{tenant_id}/integrations/{connection_id}/rotate-secret", response_model=IntegrationConnectionRead
)
def rotate_signing_secret(
    connection_id: uuid.UUID,
    payload: IntegrationSecretRotateRequest,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IntegrationConnectionRead:
    connection = _get_connection_or_404(db, ctx, connection_id)
    try:
        integration_connection_service.rotate_signing_secret(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            connection=connection,
            new_secret=payload.new_secret,
            expected_version=payload.expected_version,
            settings=settings,
        )
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return IntegrationConnectionRead.from_model(connection)


@router.post(
    "/tenants/{tenant_id}/integrations/{connection_id}/inbound-key", response_model=InboundApiKeyCreatedResponse
)
def generate_inbound_api_key(
    connection_id: uuid.UUID,
    payload: IntegrationVersionedActionRequest,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InboundApiKeyCreatedResponse:
    connection = _get_connection_or_404(db, ctx, connection_id)
    try:
        raw_key = integration_connection_service.generate_inbound_api_key(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            connection=connection,
            expected_version=payload.expected_version,
            settings=settings,
        )
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return InboundApiKeyCreatedResponse(
        api_key=raw_key,
        prefix=connection.inbound_api_key_prefix or "",
        last_four=connection.inbound_api_key_last_four or "",
    )


@router.post("/tenants/{tenant_id}/integrations/{connection_id}/pause", response_model=IntegrationConnectionRead)
def pause_integration_connection(
    connection_id: uuid.UUID,
    payload: IntegrationVersionedActionRequest,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IntegrationConnectionRead:
    connection = _get_connection_or_404(db, ctx, connection_id)
    try:
        integration_connection_service.pause_connection(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            connection=connection,
            expected_version=payload.expected_version,
        )
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return IntegrationConnectionRead.from_model(connection)


@router.post("/tenants/{tenant_id}/integrations/{connection_id}/resume", response_model=IntegrationConnectionRead)
def resume_integration_connection(
    connection_id: uuid.UUID,
    payload: IntegrationVersionedActionRequest,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IntegrationConnectionRead:
    connection = _get_connection_or_404(db, ctx, connection_id)
    try:
        integration_connection_service.resume_connection(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            connection=connection,
            expected_version=payload.expected_version,
        )
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return IntegrationConnectionRead.from_model(connection)


@router.post("/tenants/{tenant_id}/integrations/{connection_id}/disable", response_model=IntegrationConnectionRead)
def disable_integration_connection(
    connection_id: uuid.UUID,
    payload: IntegrationVersionedActionRequest,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IntegrationConnectionRead:
    connection = _get_connection_or_404(db, ctx, connection_id)
    try:
        integration_connection_service.disable_connection(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            connection=connection,
            expected_version=payload.expected_version,
        )
    except VersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return IntegrationConnectionRead.from_model(connection)


@router.post(
    "/tenants/{tenant_id}/integrations/{connection_id}/preview-mapping",
    response_model=FieldMappingPreviewResponse,
)
def preview_field_mapping_for_connection(
    connection_id: uuid.UUID,
    payload: FieldMappingPreviewRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FieldMappingPreviewResponse:
    """Read-only — any active member may preview a mapping (it never
    touches a real event or a real destination; see
    app/integrations/field_mapping.py). `sample_data` must be fictional
    data the caller supplies, never a real captured payload — this route
    performs no lookup of real event history."""
    _get_connection_or_404(db, ctx, connection_id)
    try:
        result = preview_field_mapping(payload.sample_data, payload.field_mapping or None, settings=settings)
    except FieldMappingError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return FieldMappingPreviewResponse(result=result)


@router.post(
    "/tenants/{tenant_id}/integrations/{connection_id}/process-pending",
    response_model=ProcessPendingNowResponse,
)
def process_pending_now(
    connection_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProcessPendingNowResponse:
    """An on-demand, synchronous delivery pass scoped to exactly this
    tenant and this connection — never another tenant's or another
    connection's backlog (see
    IntegrationOutboxEventRepository.claim_batch's scoping). Used by the
    integration lab so a demo doesn't require running the CLI worker
    separately; also usable as a general "process now" convenience. This
    is NOT a scheduler — it runs exactly once per call."""
    connection = _get_connection_or_404(db, ctx, connection_id)
    result = integration_connection_service.process_pending_now(
        db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, connection=connection, settings=settings
    )
    db.commit()
    return ProcessPendingNowResponse(
        claimed=result.claimed, delivered=result.delivered, retried=result.retried, dead_lettered=result.dead_lettered
    )


@router.post("/tenants/{tenant_id}/integrations/{connection_id}/verify", response_model=IntegrationVerifyResponse)
def verify_integration_connection(
    connection_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IntegrationVerifyResponse:
    connection = _get_connection_or_404(db, ctx, connection_id)
    try:
        outcome = integration_connection_service.verify_connection_now(
            db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, connection=connection, settings=settings
        )
    except SecretDecryptionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return IntegrationVerifyResponse(success=outcome.success, error_summary=outcome.error_summary)


@router.post("/tenants/{tenant_id}/integrations/{connection_id}/test-event", response_model=IntegrationOutboxEventRead)
def send_test_event(
    connection_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IntegrationOutboxEventRead:
    connection = _get_connection_or_404(db, ctx, connection_id)
    row = integration_connection_service.send_test_event(
        db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, connection=connection
    )
    db.commit()
    return IntegrationOutboxEventRead.from_model(row)


@router.get(
    "/tenants/{tenant_id}/integrations/{connection_id}/deliveries", response_model=IntegrationDeliveryListResponse
)
def list_deliveries(
    connection_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> IntegrationDeliveryListResponse:
    _get_connection_or_404(db, ctx, connection_id)
    repo = IntegrationOutboxEventRepository(db)
    rows, total = repo.list_for_connection(
        tenant_id=ctx.tenant_id, connection_id=connection_id, limit=limit, offset=offset
    )
    return IntegrationDeliveryListResponse(
        items=[IntegrationOutboxEventRead.from_model(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/tenants/{tenant_id}/integrations/{connection_id}/deliveries/{event_id}/replay",
    response_model=IntegrationOutboxEventRead,
)
def replay_dead_lettered_delivery(
    connection_id: uuid.UUID,
    event_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IntegrationOutboxEventRead:
    _get_connection_or_404(db, ctx, connection_id)
    repo = IntegrationOutboxEventRepository(db)
    row = repo.get_for_tenant(ctx.tenant_id, event_id)
    if row is None or row.connection_id != connection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")
    replayed = integration_connection_service.replay_dead_letter(
        db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, event_id=event_id
    )
    if not replayed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only a dead-lettered delivery can be replayed."
        )
    db.commit()
    db.refresh(row)
    return IntegrationOutboxEventRead.from_model(row)

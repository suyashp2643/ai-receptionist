import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_safety import MAX_SHORT_TEXT, validate_plain_text


class IntegrationConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_type: str
    name: str = Field(max_length=MAX_SHORT_TEXT)
    config: dict = Field(default_factory=dict)
    enabled_event_types: list[str] = Field(default_factory=list)
    signing_secret: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_SHORT_TEXT)


class IntegrationConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict = Field(default_factory=dict)
    enabled_event_types: list[str] = Field(default_factory=list)
    expected_version: int


class IntegrationSecretRotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_secret: str = Field(min_length=1, max_length=500)
    expected_version: int


class IntegrationVersionedActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int


class IntegrationConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_type: str
    name: str
    status: str
    config: dict
    enabled_event_types: list[str]
    has_signing_secret: bool
    inbound_api_key_prefix: str | None
    inbound_api_key_last_four: str | None
    failure_count: int
    last_verified_at: datetime | None
    last_delivery_at: datetime | None
    last_delivery_status: str | None
    last_inbound_event_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, connection) -> "IntegrationConnectionRead":  # noqa: ANN001
        return cls(
            id=connection.id,
            connector_type=connection.connector_type.value,
            name=connection.name,
            status=connection.status.value,
            config=connection.config,
            enabled_event_types=list(connection.enabled_event_types),
            has_signing_secret=bool(connection.signing_secret_ciphertext),
            inbound_api_key_prefix=connection.inbound_api_key_prefix,
            inbound_api_key_last_four=connection.inbound_api_key_last_four,
            failure_count=connection.failure_count,
            last_verified_at=connection.last_verified_at,
            last_delivery_at=connection.last_delivery_at,
            last_delivery_status=connection.last_delivery_status.value if connection.last_delivery_status else None,
            last_inbound_event_at=connection.last_inbound_event_at,
            version=connection.version,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
        )


class IntegrationConnectionListResponse(BaseModel):
    items: list[IntegrationConnectionRead]


class InboundApiKeyCreatedResponse(BaseModel):
    """The raw key is present ONLY in this one response — never again,
    never logged, never retrievable afterward."""

    api_key: str
    prefix: str
    last_four: str


class IntegrationVerifyResponse(BaseModel):
    success: bool
    error_summary: str | None


class IntegrationDeliveryAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attempt_number: int
    status: str
    http_status_code: int | None
    error_summary: str | None
    duration_ms: int | None
    created_at: datetime

    @classmethod
    def from_model(cls, attempt) -> "IntegrationDeliveryAttemptRead":  # noqa: ANN001
        return cls(
            id=attempt.id,
            attempt_number=attempt.attempt_number,
            status=attempt.status.value,
            http_status_code=attempt.http_status_code,
            error_summary=attempt.error_summary,
            duration_ms=attempt.duration_ms,
            created_at=attempt.created_at,
        )


class IntegrationOutboxEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    event_version: int
    status: str
    attempt_count: int
    available_at: datetime
    delivered_at: datetime | None
    dead_lettered_at: datetime | None
    last_error: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, event) -> "IntegrationOutboxEventRead":  # noqa: ANN001
        return cls(
            id=event.id,
            event_type=event.event_type,
            event_version=event.event_version,
            status=event.status.value,
            attempt_count=event.attempt_count,
            available_at=event.available_at,
            delivered_at=event.delivered_at,
            dead_lettered_at=event.dead_lettered_at,
            last_error=event.last_error,
            created_at=event.created_at,
        )


class IntegrationDeliveryListResponse(BaseModel):
    items: list[IntegrationOutboxEventRead]
    total: int
    limit: int
    offset: int


class FieldMappingPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_data: dict = Field(default_factory=dict)
    field_mapping: dict = Field(default_factory=dict)


class FieldMappingPreviewResponse(BaseModel):
    result: dict


class ProcessPendingNowResponse(BaseModel):
    claimed: int
    delivered: int
    retried: int
    dead_lettered: int


class ConnectionStatusBreakdownRead(BaseModel):
    active: int
    paused: int
    failing: int
    disabled: int
    total: int


class DeliveryLatencySummaryRead(BaseModel):
    p50_ms: float | None
    p95_ms: float | None
    sample_size: int


class HealthWarningRead(BaseModel):
    code: str
    message: str
    connection_id: uuid.UUID | None


class TenantIntegrationHealthRead(BaseModel):
    window_hours: int
    connections: ConnectionStatusBreakdownRead
    pending_events: int
    retry_backlog: int
    oldest_pending_age_seconds: float | None
    dead_letter_count: int
    successful_deliveries: int
    failed_deliveries: int
    success_rate: float | None
    latency: DeliveryLatencySummaryRead
    last_success_at: datetime | None
    last_failure_at: datetime | None
    warnings: list[HealthWarningRead]

    @classmethod
    def from_health(cls, health) -> "TenantIntegrationHealthRead":  # noqa: ANN001
        return cls(
            window_hours=health.window_hours,
            connections=ConnectionStatusBreakdownRead(**vars(health.connections)),
            pending_events=health.pending_events,
            retry_backlog=health.retry_backlog,
            oldest_pending_age_seconds=health.oldest_pending_age_seconds,
            dead_letter_count=health.dead_letter_count,
            successful_deliveries=health.successful_deliveries,
            failed_deliveries=health.failed_deliveries,
            success_rate=health.success_rate,
            latency=DeliveryLatencySummaryRead(**vars(health.latency)),
            last_success_at=health.last_success_at,
            last_failure_at=health.last_failure_at,
            warnings=[HealthWarningRead(**vars(w)) for w in health.warnings],
        )

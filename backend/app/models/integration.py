"""Phase 8: the integration foundation connecting this app to Revenue
Brain, the future AI Sales Employee, and generic webhook receivers.

Four tables, deliberately kept together in one module since they only ever
make sense read as a set (see docs/integration-contracts.md for the full
design write-up):

  IntegrationConnection    — one tenant-configured connector (who/where/how)
  IntegrationOutboxEvent   — the transactional outbox: one row per
                              (domain event, connection) pair awaiting
                              delivery
  IntegrationDeliveryAttempt — permanent, append-only history of every
                              delivery attempt made for an outbox row
  InboundIntegrationEvent  — permanent, append-only record of every inbound
                              call accepted (or rejected) through a
                              connection's inbound credential

Design decision worth calling out: IntegrationOutboxEvent is per-connection,
not per-domain-event. A service producing a domain event (e.g. "enquiry
qualified") writes one outbox row per tenant connection subscribed to that
event type, inside the same transaction as the domain mutation — not one
shared row fanned out later. This trades a small amount of storage
duplication (the same JSONB payload once per subscribed connection) for a
delivery worker that can claim, deliver, and retry a single row against a
single connector with no join or fan-out step — simpler to reason about,
and it keeps `FOR UPDATE SKIP LOCKED` claiming trivial. See
app/services/outbox_producer_service.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    DeliveryAttemptStatus,
    InboundEventStatus,
    IntegrationConnectionStatus,
    IntegrationConnectorType,
    OutboxEventStatus,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


def _native_enum(enum_cls: type, name: str) -> SAEnum:
    return SAEnum(enum_cls, name=name, native_enum=True, values_callable=lambda cls: [m.value for m in cls])


class IntegrationConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant-configured connector to an external system. Never stores a
    secret in plaintext: `signing_secret_ciphertext` is Fernet-encrypted
    (see app/core/crypto.py) and `inbound_api_key_hash` is a SHA-256 hash of
    a key shown to the owner/admin exactly once at creation/rotation time.

    `config` holds only non-secret connector configuration (destination
    URL, field mapping, custom headers to attach) — validated by the
    connector's own schema before being stored (see
    app/integrations/connectors/base.py). It is never treated as trusted
    input by any code path that executes it: field mapping supports only
    rename/include/omit/default (app/integrations/field_mapping.py), no
    expression evaluation.

    `status` is one of five mutually exclusive states — see
    IntegrationConnectionStatus's own docstring in app/models/enums.py for
    the exact promotion/demotion rules. There is no boolean "connected"
    flag anywhere in this schema on purpose.
    """

    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_integration_connections_tenant_name"),
        Index("ix_integration_connections_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_type: Mapped[IntegrationConnectorType] = mapped_column(
        _native_enum(IntegrationConnectorType, "integration_connector_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[IntegrationConnectionStatus] = mapped_column(
        _native_enum(IntegrationConnectionStatus, "integration_connection_status"),
        nullable=False,
        default=IntegrationConnectionStatus.CONFIGURED,
    )

    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    enabled_event_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Outbound webhook/HMAC signing secret, encrypted at rest. Both columns
    # are null for a connector type that has no signing secret (e.g. mock).
    signing_secret_ciphertext: Mapped[str | None] = mapped_column(String(2000))
    signing_secret_key_version: Mapped[int | None] = mapped_column(Integer)

    # Inbound credential — lets Revenue Brain / Sales Employee / a generic
    # caller push events INTO this connection. Only the hash is stored; see
    # app/core/crypto.py::generate_api_key / hash_api_key. prefix/last_four
    # are display-only, never enough to reconstruct the key. Unique + indexed:
    # the inbound API route (app/api/v1/integrations_inbound.py) has no
    # tenant_id in its URL by design (tenant scope comes from the credential
    # alone), so it must look up the owning connection by this hash directly,
    # in a single indexed query — never a full-table scan.
    inbound_api_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    inbound_api_key_prefix: Mapped[str | None] = mapped_column(String(20))
    inbound_api_key_last_four: Mapped[str | None] = mapped_column(String(4))
    inbound_api_key_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inbound_api_key_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Health signal, not a delivery gate — see INTEGRATION_DELIVERABLE_STATUSES.
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_delivery_status: Mapped[DeliveryAttemptStatus | None] = mapped_column(
        _native_enum(DeliveryAttemptStatus, "integration_last_delivery_status")
    )
    last_inbound_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    # Optimistic concurrency — same pattern as Enquiry.version. Every
    # mutating dashboard action (pause/disable/rotate/edit mapping) must
    # supply the version it read.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def __repr__(self) -> str:
        return f"IntegrationConnection(id={self.id!r}, tenant_id={self.tenant_id!r}, name={self.name!r})"


class IntegrationOutboxEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per (domain event, subscribed connection) pair. See this
    module's docstring for why the outbox is per-connection rather than
    shared. `event_id` is the envelope's own identity — shared across every
    connection's row for the same underlying occurrence — while `id` (this
    row's own primary key) is unique per connection.

    `dedup_key` is chosen by the producer (see
    app/services/outbox_producer_service.py) to be stable across retried
    production attempts for the same underlying domain event, e.g.
    `f"{event_type}:{entity_id}:{entity_version}"`; the unique constraint
    below makes duplicate production a no-op at the database level rather
    than relying on application logic alone.
    """

    __tablename__ = "integration_outbox_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "connection_id", "dedup_key", name="uq_integration_outbox_events_tenant_conn_dedup"
        ),
        # Backs the worker's claim query: WHERE status = 'pending' AND
        # available_at <= now() ORDER BY available_at — and the lease-expiry
        # recovery query, which additionally filters status = 'claimed' AND
        # lease_expires_at <= now(). One composite index serves both since
        # status is always the leading, highly selective column.
        Index("ix_integration_outbox_events_claim", "status", "available_at"),
        Index("ix_integration_outbox_events_connection", "connection_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False
    )

    event_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(300), nullable=False)

    # The full versioned envelope (see app/integrations/envelope.py) —
    # already validated and PII/consent-scope-checked at production time.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[OutboxEventStatus] = mapped_column(
        _native_enum(OutboxEventStatus, "integration_outbox_event_status"),
        nullable=False,
        default=OutboxEventStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Backoff scheduling: a row is claimable once available_at <= now().
    # Set to now() at creation, pushed forward on each retryable failure.
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Short, safe summary only — never a raw response body or secret.
    last_error: Mapped[str | None] = mapped_column(String(1000))

    def __repr__(self) -> str:
        return f"IntegrationOutboxEvent(id={self.id!r}, event_type={self.event_type!r}, status={self.status!r})"


class IntegrationDeliveryAttempt(UUIDPrimaryKeyMixin, Base):
    """Permanent, append-only history of every delivery attempt — never
    mutated after creation, unlike the outbox row's own status. Mirrors
    ActivityEvent's append-only shape (no TimestampMixin/updated_at)."""

    __tablename__ = "integration_delivery_attempts"
    __table_args__ = (Index("ix_integration_delivery_attempts_outbox", "outbox_event_id", "attempt_number"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outbox_event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("integration_outbox_events.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DeliveryAttemptStatus] = mapped_column(
        _native_enum(DeliveryAttemptStatus, "integration_delivery_attempt_status"), nullable=False
    )
    http_status_code: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(String(1000))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"IntegrationDeliveryAttempt(id={self.id!r}, outbox_event_id={self.outbox_event_id!r})"


class InboundIntegrationEvent(UUIDPrimaryKeyMixin, Base):
    """Permanent, append-only record of every inbound call accepted or
    rejected through a connection's inbound API key. `payload_hash` (not
    the payload itself) plus `external_event_id` back the inbound
    idempotency check in app/api/v1/integrations_inbound.py: a repeat POST
    with the same external_event_id and the same payload_hash is a
    harmless replay; the same external_event_id with a DIFFERENT
    payload_hash is a conflict, surfaced as a 409, never silently
    processed as an update."""

    __tablename__ = "inbound_integration_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "connection_id", "external_event_id", name="uq_inbound_integration_events_tenant_conn_ext"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False
    )

    external_event_id: Mapped[str] = mapped_column(String(300), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InboundEventStatus] = mapped_column(
        _native_enum(InboundEventStatus, "inbound_integration_event_status"), nullable=False
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"InboundIntegrationEvent(id={self.id!r}, event_type={self.event_type!r}, status={self.status!r})"

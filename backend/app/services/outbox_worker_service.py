"""The outbox delivery worker: claims due IntegrationOutboxEvent rows and
attempts delivery. Zero paid infrastructure — this is an in-process
Python function, invoked repeatedly by a bounded local loop or a single
CLI invocation (see backend/scripts/process_integration_outbox.py), never
a message broker.

Transaction shape, deliberately mirroring the conversation orchestrator's
own 3-phase-commit precedent (app/ai/orchestrator.py) of never holding a
DB lock across a network call:

  1. `claim_batch` — one short transaction. Claims rows via
     `FOR UPDATE SKIP LOCKED` (app/repositories/integration.py), extracts
     every value delivery needs into plain `ClaimedOutboxItem`s, commits
     (releasing the row locks), and returns.
  2. For each claimed item: a second short transaction loads the
     connection's config/secret, extracts them into plain local values,
     and commits/closes BEFORE any network call — an ORM instance is never
     touched after its owning session closes (SQLAlchemy's default
     `expire_on_commit=True` would raise `DetachedInstanceError`), so
     everything the delivery call needs is captured into plain variables
     first.
  3. `connector.deliver(...)` — the actual HTTP call, entirely outside any
     DB session.
  4. A third short transaction records the IntegrationDeliveryAttempt and
     updates the outbox row's status (delivered / retried with backoff /
     dead-lettered) and the connection's health fields.

Known limitation, documented rather than engineered around: step 4's
connection health-field update (`failure_count`, `last_delivery_status`)
is a plain read-modify-write, not a SQL-level atomic increment — under
concurrent deliveries for the SAME connection this can lose an increment.
Acceptable because these fields are an operator-facing health signal, not
a delivery gate or a security boundary (see
IntegrationConnectionStatus's docstring in app/models/enums.py) and not
worth the added complexity of a conditional atomic increment for a
best-effort counter.
"""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.core.crypto import SecretDecryptionError, decrypt_secret
from app.db.session import session_scope
from app.integrations.backoff import compute_backoff_seconds
from app.integrations.connectors.factory import get_connector
from app.integrations.envelope import EventEnvelope
from app.models.enums import DeliveryAttemptStatus, IntegrationConnectionStatus, IntegrationConnectorType
from app.models.integration import IntegrationConnection, IntegrationDeliveryAttempt
from app.repositories.integration import IntegrationOutboxEventRepository

_CONSECUTIVE_FAILURES_BEFORE_FAILING = 3


def _worker_instance_id() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class ClaimedOutboxItem:
    id: uuid.UUID
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    attempt_count: int
    payload: dict


@dataclass(frozen=True)
class _ConnectionSnapshot:
    connector_type: IntegrationConnectorType
    config: dict
    secret: str | None
    secret_undecryptable: bool


@dataclass
class WorkerBatchResult:
    claimed: int = 0
    delivered: int = 0
    retried: int = 0
    dead_lettered: int = 0
    skipped_missing_connection: int = 0


def claim_batch(
    *,
    settings: Settings,
    worker_id: str | None = None,
    tenant_id: uuid.UUID | None = None,
    connection_id: uuid.UUID | None = None,
    batch_size: int | None = None,
) -> list[ClaimedOutboxItem]:
    worker_id = worker_id or _worker_instance_id()
    with session_scope() as db:
        repo = IntegrationOutboxEventRepository(db)
        rows = repo.claim_batch(
            batch_size=batch_size or settings.integration_worker_batch_size,
            lease_seconds=settings.integration_lease_seconds,
            worker_id=worker_id,
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
        return [
            ClaimedOutboxItem(
                id=row.id,
                tenant_id=row.tenant_id,
                connection_id=row.connection_id,
                attempt_count=row.attempt_count,
                payload=row.payload,
            )
            for row in rows
        ]


def _load_connection_snapshot(
    connection: IntegrationConnection | None, *, settings: Settings
) -> _ConnectionSnapshot | None:
    if connection is None:
        return None
    secret: str | None = None
    undecryptable = False
    if connection.signing_secret_ciphertext:
        try:
            secret = decrypt_secret(
                connection.signing_secret_ciphertext,
                key_version=connection.signing_secret_key_version or 0,
                settings=settings,
            )
        except SecretDecryptionError:
            undecryptable = True
    return _ConnectionSnapshot(
        connector_type=connection.connector_type,
        config=dict(connection.config),
        secret=secret,
        secret_undecryptable=undecryptable,
    )


def _deliver_one(item: ClaimedOutboxItem, *, settings: Settings) -> WorkerBatchResult:
    result = WorkerBatchResult()

    with session_scope() as db:
        connection = db.get(IntegrationConnection, item.connection_id)
        if connection is None or connection.tenant_id != item.tenant_id:
            # Defense in depth, not a reachable path today: integration_outbox_events
            # has ON DELETE CASCADE on connection_id, so a connection's outbox
            # rows are always deleted in the same statement as the connection
            # itself — an outbox row can never actually outlive its connection.
            # Kept in case a future schema change relaxes that FK.
            repo = IntegrationOutboxEventRepository(db)
            repo.mark_dead_letter(item.id, error_summary="Connection no longer exists.")
            result.skipped_missing_connection = 1
            result.dead_lettered = 1
            return result
        snapshot = _load_connection_snapshot(connection, settings=settings)

    assert snapshot is not None  # the None-connection path already returned above

    if snapshot.secret_undecryptable:
        outcome_status = DeliveryAttemptStatus.PERMANENT_FAILURE
        error_summary: str | None = "Stored signing secret could not be decrypted."
        http_status_code: int | None = None
        duration_ms = 0
    else:
        envelope = EventEnvelope.model_validate(item.payload)
        delivery_id = uuid.uuid4()
        connector = get_connector(snapshot.connector_type)
        outcome = connector.deliver(
            config=snapshot.config,
            secret=snapshot.secret,
            envelope=envelope,
            delivery_id=delivery_id,
            settings=settings,
        )
        outcome_status = outcome.status
        error_summary = outcome.error_summary
        http_status_code = outcome.http_status_code
        duration_ms = outcome.duration_ms

    with session_scope() as db:
        outbox_repo = IntegrationOutboxEventRepository(db)
        db.add(
            IntegrationDeliveryAttempt(
                tenant_id=item.tenant_id,
                outbox_event_id=item.id,
                connection_id=item.connection_id,
                attempt_number=item.attempt_count,
                status=outcome_status,
                http_status_code=http_status_code,
                error_summary=error_summary,
                duration_ms=duration_ms,
            )
        )

        connection = db.get(IntegrationConnection, item.connection_id)
        now = datetime.now(UTC)
        if outcome_status == DeliveryAttemptStatus.SUCCESS:
            outbox_repo.mark_delivered(item.id)
            result.delivered = 1
            if connection is not None:
                connection.failure_count = 0
                connection.last_delivery_at = now
                connection.last_delivery_status = DeliveryAttemptStatus.SUCCESS
                if connection.status in (
                    IntegrationConnectionStatus.CONFIGURED,
                    IntegrationConnectionStatus.FAILING,
                ):
                    connection.status = IntegrationConnectionStatus.VERIFIED
                connection.last_verified_at = now
                connection.version += 1
        else:
            if connection is not None:
                connection.failure_count += 1
                connection.last_delivery_at = now
                connection.last_delivery_status = outcome_status
                if (
                    connection.status == IntegrationConnectionStatus.VERIFIED
                    and connection.failure_count >= _CONSECUTIVE_FAILURES_BEFORE_FAILING
                ):
                    connection.status = IntegrationConnectionStatus.FAILING
                connection.version += 1

            exhausted = item.attempt_count >= settings.integration_max_delivery_attempts
            if outcome_status == DeliveryAttemptStatus.PERMANENT_FAILURE or exhausted:
                outbox_repo.mark_dead_letter(item.id, error_summary=error_summary or "Delivery failed.")
                result.dead_lettered = 1
            else:
                delay = compute_backoff_seconds(
                    item.attempt_count,
                    base_seconds=settings.integration_backoff_base_seconds,
                    max_seconds=settings.integration_backoff_max_seconds,
                )
                outbox_repo.mark_retry(
                    item.id,
                    next_available_at=now + timedelta(seconds=delay),
                    error_summary=error_summary or "Delivery failed.",
                )
                result.retried = 1
    return result


def run_once(
    *,
    settings: Settings,
    worker_id: str | None = None,
    tenant_id: uuid.UUID | None = None,
    connection_id: uuid.UUID | None = None,
    batch_size: int | None = None,
) -> WorkerBatchResult:
    """Claims one batch and attempts delivery for each claimed row. Safe to
    call repeatedly (a polling loop, a scheduled CLI invocation, or a cron
    job) — every claim/deliver/record cycle is fully self-contained and
    idempotent-safe (a crash between steps leaves a row either still
    PENDING or CLAIMED-with-an-expiring-lease, never lost).

    `tenant_id`/`connection_id` narrow processing to one tenant (and, with
    both set, one connection) — see `claim_batch`'s own docstring. Omit
    both for the real background worker's global claim."""
    worker_id = worker_id or _worker_instance_id()
    items = claim_batch(
        settings=settings, worker_id=worker_id, tenant_id=tenant_id, connection_id=connection_id, batch_size=batch_size
    )
    total = WorkerBatchResult(claimed=len(items))
    for item in items:
        outcome = _deliver_one(item, settings=settings)
        total.delivered += outcome.delivered
        total.retried += outcome.retried
        total.dead_lettered += outcome.dead_lettered
        total.skipped_missing_connection += outcome.skipped_missing_connection
    return total

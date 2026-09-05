import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.enums import DeliveryAttemptStatus, OutboxEventStatus
from app.models.integration import (
    InboundIntegrationEvent,
    IntegrationConnection,
    IntegrationDeliveryAttempt,
    IntegrationOutboxEvent,
)
from app.repositories.base import TenantScopedRepository


def find_connection_by_inbound_api_key_hash(db: Session, key_hash: str) -> IntegrationConnection | None:
    """Deliberately NOT a TenantScopedRepository method: the inbound
    integration API (app/api/v1/integrations_inbound.py) has no tenant_id
    in its URL by design — tenant scope comes from the credential alone —
    so this is the one place a connection is looked up by hash across every
    tenant. Backed by the unique index on inbound_api_key_hash (see the
    model), never a full-table scan."""
    stmt = select(IntegrationConnection).where(IntegrationConnection.inbound_api_key_hash == key_hash)
    return db.scalars(stmt).first()


class IntegrationConnectionRepository(TenantScopedRepository[IntegrationConnection]):  # type: ignore[type-var]
    model = IntegrationConnection

    def list_recent(self, *, limit: int, offset: int) -> Sequence[IntegrationConnection]:
        stmt = (
            select(IntegrationConnection)
            .where(IntegrationConnection.tenant_id == self.tenant_id)
            .order_by(IntegrationConnection.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all()

    def get_by_name(self, name: str) -> IntegrationConnection | None:
        stmt = select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == self.tenant_id, IntegrationConnection.name == name
        )
        return self.db.scalars(stmt).first()

    def list_subscribed(self, event_type: str) -> Sequence[IntegrationConnection]:
        """Connections for this tenant that (a) are in a deliverable status
        and (b) have `event_type` in their enabled_event_types. The status
        filter is a Python-side membership check against
        INTEGRATION_DELIVERABLE_STATUSES applied by the caller — this method
        only applies the tenant + event-type-subscription filter, which
        Postgres can evaluate directly on the JSONB column."""
        stmt = select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == self.tenant_id,
            IntegrationConnection.enabled_event_types.contains([event_type]),
        )
        return self.db.scalars(stmt).all()


class IntegrationOutboxEventRepository:
    """Deliberately NOT tenant-scoped: the delivery worker claims a batch of
    due rows across every tenant in one query — see claim_batch below. Any
    tenant-scoped read (e.g. a dashboard delivery-history view) goes
    through a query that itself filters by tenant_id explicitly rather than
    through TenantScopedRepository, per that class's own docstring on when
    to bypass it."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, obj: IntegrationOutboxEvent) -> IntegrationOutboxEvent:
        self.db.add(obj)
        return obj

    def get_for_tenant(self, tenant_id: uuid.UUID, event_id: uuid.UUID) -> IntegrationOutboxEvent | None:
        stmt = select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.tenant_id == tenant_id, IntegrationOutboxEvent.id == event_id
        )
        return self.db.scalars(stmt).first()

    def list_for_connection(
        self, *, tenant_id: uuid.UUID, connection_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[Sequence[IntegrationOutboxEvent], int]:
        conditions = (
            IntegrationOutboxEvent.tenant_id == tenant_id,
            IntegrationOutboxEvent.connection_id == connection_id,
        )
        total = self.db.scalar(select(func.count()).select_from(IntegrationOutboxEvent).where(*conditions)) or 0
        stmt = (
            select(IntegrationOutboxEvent)
            .where(*conditions)
            .order_by(IntegrationOutboxEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all(), total

    def claim_batch(
        self,
        *,
        batch_size: int,
        lease_seconds: int,
        worker_id: str,
        tenant_id: uuid.UUID | None = None,
        connection_id: uuid.UUID | None = None,
    ) -> Sequence[IntegrationOutboxEvent]:
        """Atomically claims up to `batch_size` due rows — either freshly
        PENDING (available_at has passed) or CLAIMED-but-abandoned (their
        lease expired, meaning the worker that claimed them crashed or was
        killed before finishing). `FOR UPDATE SKIP LOCKED` on the inner
        SELECT means a second, concurrently-running worker calling this at
        the same instant skips any row this call has already locked rather
        than blocking on it or double-claiming it — see
        docs/architecture.md's Phase 8 concurrency section and the
        multiconn test that exercises this with real separate connections
        (tests/integration/test_phase8_outbox_worker.py).

        The row lock is held only for the duration of this single UPDATE —
        never across the network call that follows, matching the
        orchestrator's own 3-phase-commit precedent of never holding a lock
        during I/O.

        `tenant_id`/`connection_id` narrow the claim to one tenant (and,
        with both set, one connection) — used by the dashboard's
        authenticated "process now" action (app/api/v1/integrations.py)
        and the integration lab, so a click in one tenant's dashboard can
        never claim or process another tenant's backlog. The background
        worker (app/services/outbox_worker_service.py) always omits both,
        claiming globally across every tenant, exactly as before."""
        now = datetime.now(UTC)
        conditions = [
            or_(
                and_(
                    IntegrationOutboxEvent.status == OutboxEventStatus.PENDING,
                    IntegrationOutboxEvent.available_at <= now,
                ),
                and_(
                    IntegrationOutboxEvent.status == OutboxEventStatus.CLAIMED,
                    IntegrationOutboxEvent.lease_expires_at <= now,
                ),
            )
        ]
        if tenant_id is not None:
            conditions.append(IntegrationOutboxEvent.tenant_id == tenant_id)
        if connection_id is not None:
            conditions.append(IntegrationOutboxEvent.connection_id == connection_id)

        claimable = (
            select(IntegrationOutboxEvent.id)
            .where(*conditions)
            .order_by(IntegrationOutboxEvent.available_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        stmt = (
            update(IntegrationOutboxEvent)
            .where(IntegrationOutboxEvent.id.in_(claimable))
            .values(
                status=OutboxEventStatus.CLAIMED,
                claimed_at=now,
                claimed_by=worker_id,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempt_count=IntegrationOutboxEvent.attempt_count + 1,
            )
            .returning(IntegrationOutboxEvent)
        )
        result = self.db.execute(stmt)
        return result.scalars().all()

    def mark_delivered(self, event_id: uuid.UUID) -> None:
        self.db.execute(
            update(IntegrationOutboxEvent)
            .where(IntegrationOutboxEvent.id == event_id)
            .values(status=OutboxEventStatus.DELIVERED, delivered_at=datetime.now(UTC), last_error=None)
        )

    def mark_retry(self, event_id: uuid.UUID, *, next_available_at: datetime, error_summary: str) -> None:
        self.db.execute(
            update(IntegrationOutboxEvent)
            .where(IntegrationOutboxEvent.id == event_id)
            .values(
                status=OutboxEventStatus.PENDING,
                available_at=next_available_at,
                claimed_at=None,
                claimed_by=None,
                lease_expires_at=None,
                last_error=error_summary[:1000],
            )
        )

    def mark_dead_letter(self, event_id: uuid.UUID, *, error_summary: str) -> None:
        self.db.execute(
            update(IntegrationOutboxEvent)
            .where(IntegrationOutboxEvent.id == event_id)
            .values(
                status=OutboxEventStatus.DEAD_LETTER,
                dead_lettered_at=datetime.now(UTC),
                last_error=error_summary[:1000],
            )
        )

    def replay_dead_letter(self, *, tenant_id: uuid.UUID, event_id: uuid.UUID) -> bool:
        """Re-queues a dead-lettered row for another delivery attempt —
        used only by the authorized dashboard/CLI replay action, never
        automatically. Returns False if the row doesn't exist, isn't this
        tenant's, or isn't currently dead-lettered (so a caller can't
        accidentally "replay" a row that's already pending/claimed)."""
        result = self.db.execute(
            update(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.id == event_id,
                IntegrationOutboxEvent.tenant_id == tenant_id,
                IntegrationOutboxEvent.status == OutboxEventStatus.DEAD_LETTER,
            )
            .values(
                status=OutboxEventStatus.PENDING,
                available_at=datetime.now(UTC),
                dead_lettered_at=None,
                last_error=None,
            )
        )
        return result.rowcount == 1

    def count_by_status(self) -> dict[str, int]:
        stmt = select(IntegrationOutboxEvent.status, func.count()).group_by(IntegrationOutboxEvent.status)
        return {status.value: count for status, count in self.db.execute(stmt).all()}

    def status_counts_for_tenant(self, tenant_id: uuid.UUID) -> dict[str, int]:
        """One GROUP BY query, scoped to this tenant only — never touches
        another tenant's rows, and its cost is proportional to this
        tenant's own distinct statuses (at most 4), not row count."""
        stmt = (
            select(IntegrationOutboxEvent.status, func.count())
            .where(IntegrationOutboxEvent.tenant_id == tenant_id)
            .group_by(IntegrationOutboxEvent.status)
        )
        return {status.value: count for status, count in self.db.execute(stmt).all()}

    def pending_backlog_summary(self, tenant_id: uuid.UUID) -> tuple[int, datetime | None]:
        """One aggregate-row query. Returns
        (retry_backlog_count, oldest_pending_available_at) — retry_backlog
        is PENDING rows with attempt_count > 0 (i.e. pending because of a
        retry, not merely still waiting for its first attempt);
        oldest_pending_available_at is None when nothing is pending."""
        stmt = select(
            func.count().filter(IntegrationOutboxEvent.attempt_count > 0),
            func.min(IntegrationOutboxEvent.available_at),
        ).where(
            IntegrationOutboxEvent.tenant_id == tenant_id,
            IntegrationOutboxEvent.status == OutboxEventStatus.PENDING,
        )
        retry_backlog, oldest = self.db.execute(stmt).one()
        return retry_backlog or 0, oldest


class IntegrationDeliveryAttemptRepository(TenantScopedRepository[IntegrationDeliveryAttempt]):  # type: ignore[type-var]
    model = IntegrationDeliveryAttempt

    def list_for_outbox_event(self, outbox_event_id: uuid.UUID) -> Sequence[IntegrationDeliveryAttempt]:
        stmt = (
            select(IntegrationDeliveryAttempt)
            .where(
                IntegrationDeliveryAttempt.tenant_id == self.tenant_id,
                IntegrationDeliveryAttempt.outbox_event_id == outbox_event_id,
            )
            .order_by(IntegrationDeliveryAttempt.attempt_number)
        )
        return self.db.scalars(stmt).all()

    def list_for_connection(
        self, *, connection_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[Sequence[IntegrationDeliveryAttempt], int]:
        conditions = (
            IntegrationDeliveryAttempt.tenant_id == self.tenant_id,
            IntegrationDeliveryAttempt.connection_id == connection_id,
        )
        total = self.db.scalar(select(func.count()).select_from(IntegrationDeliveryAttempt).where(*conditions)) or 0
        stmt = (
            select(IntegrationDeliveryAttempt)
            .where(*conditions)
            .order_by(IntegrationDeliveryAttempt.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all(), total

    _FAILURE_STATUSES = (DeliveryAttemptStatus.RETRYABLE_FAILURE, DeliveryAttemptStatus.PERMANENT_FAILURE)

    def window_summary(self, *, since: datetime) -> tuple[int, int]:
        """One aggregate-row query, scoped to this tenant. Returns
        (success_count, failure_count) for attempts with
        created_at >= `since` — the numerator/denominator inputs for the
        health endpoint's success rate."""
        stmt = select(
            func.count().filter(IntegrationDeliveryAttempt.status == DeliveryAttemptStatus.SUCCESS),
            func.count().filter(IntegrationDeliveryAttempt.status.in_(self._FAILURE_STATUSES)),
        ).where(IntegrationDeliveryAttempt.tenant_id == self.tenant_id, IntegrationDeliveryAttempt.created_at >= since)
        success, failure = self.db.execute(stmt).one()
        return success or 0, failure or 0

    def success_duration_sample(self, *, since: datetime, limit: int) -> Sequence[int]:
        """A bounded (LIMIT-capped) fetch of raw successful-delivery
        durations within the window, used only to estimate latency
        percentiles — never the full row set regardless of how many
        attempts occurred in the window. See
        app/services/integration_health_service.py for why this is a
        sample, not an exact percentile."""
        stmt = (
            select(IntegrationDeliveryAttempt.duration_ms)
            .where(
                IntegrationDeliveryAttempt.tenant_id == self.tenant_id,
                IntegrationDeliveryAttempt.status == DeliveryAttemptStatus.SUCCESS,
                IntegrationDeliveryAttempt.created_at >= since,
                IntegrationDeliveryAttempt.duration_ms.is_not(None),
            )
            .order_by(IntegrationDeliveryAttempt.created_at.desc())
            .limit(limit)
        )
        return [d for d in self.db.scalars(stmt).all() if d is not None]

    def last_success_and_failure(self) -> tuple[datetime | None, datetime | None]:
        """One aggregate-row query, scoped to this tenant, all-time (not
        window-bounded) — 'last success'/'last failure' are meaningful
        regardless of the reporting window."""
        stmt = select(
            func.max(IntegrationDeliveryAttempt.created_at).filter(
                IntegrationDeliveryAttempt.status == DeliveryAttemptStatus.SUCCESS
            ),
            func.max(IntegrationDeliveryAttempt.created_at).filter(
                IntegrationDeliveryAttempt.status.in_(self._FAILURE_STATUSES)
            ),
        ).where(IntegrationDeliveryAttempt.tenant_id == self.tenant_id)
        last_success, last_failure = self.db.execute(stmt).one()
        return last_success, last_failure


class InboundIntegrationEventRepository(TenantScopedRepository[InboundIntegrationEvent]):  # type: ignore[type-var]
    model = InboundIntegrationEvent

    def get_by_external_id(self, *, connection_id: uuid.UUID, external_event_id: str) -> InboundIntegrationEvent | None:
        stmt = select(InboundIntegrationEvent).where(
            InboundIntegrationEvent.tenant_id == self.tenant_id,
            InboundIntegrationEvent.connection_id == connection_id,
            InboundIntegrationEvent.external_event_id == external_event_id,
        )
        return self.db.scalars(stmt).first()

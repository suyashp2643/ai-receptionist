"""Real-database tests for the outbox delivery worker. Marked `multiconn`
(see pyproject.toml) even though most of these tests use a single thread,
because `outbox_worker_service` always opens its own real
`app.db.session.session_scope()` — bypassing `tests/conftest.py`'s
rolled-back `db_session` fixture entirely — so every row this module
creates is a real commit that MUST be cleaned up explicitly, exactly like
the existing `tests/integration/test_handoff_claim_concurrency.py`
pattern. The one genuinely concurrent test
(`test_two_workers_never_claim_the_same_row`) is the reason this suite
exists in `tests/integration/` rather than the main `tests/` tree.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.config import get_settings
from app.integrations.envelope import ContactCapturedPayload, ContactSummaryPayload, EventType
from app.models.enums import (
    DeliveryAttemptStatus,
    IntegrationConnectionStatus,
    IntegrationConnectorType,
    OutboxEventStatus,
)
from app.models.integration import IntegrationConnection, IntegrationDeliveryAttempt, IntegrationOutboxEvent
from app.models.tenant import Tenant
from app.services import outbox_producer_service, outbox_worker_service
from sqlalchemy import select, text

from tests.integration.conftest import held_locks_on, idle_in_transaction_count

pytestmark = pytest.mark.multiconn

settings = get_settings()


def _make_tenant_and_connection(
    db, *, connector_type=IntegrationConnectorType.MOCK, mode="success", status=IntegrationConnectionStatus.CONFIGURED
):
    tenant = Tenant(name="Phase8 Worker Test", slug=f"phase8-worker-{uuid.uuid4().hex[:10]}")
    db.add(tenant)
    db.flush()
    connection = IntegrationConnection(
        tenant_id=tenant.id,
        connector_type=connector_type,
        name="Worker Test Connection",
        status=status,
        config={"mode": mode},
        enabled_event_types=["contact.captured"],
    )
    db.add(connection)
    db.flush()
    return tenant, connection


def _contact_payload():
    return ContactCapturedPayload(
        contact=ContactSummaryPayload(contact_id=uuid.uuid4(), marketing_consent=False, source="widget")
    )


@pytest.fixture()
def db(multiconn_engine):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=multiconn_engine)
    session = factory()
    yield session
    session.close()


@pytest.fixture()
def cleanup(multiconn_engine):
    tenant_ids: list[str] = []
    yield tenant_ids
    if tenant_ids:
        with multiconn_engine.begin() as conn:
            conn.execute(text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": tenant_ids})


class TestSuccessfulDelivery:
    def test_claims_delivers_and_marks_delivered(self, db, cleanup):
        tenant, connection = _make_tenant_and_connection(db, mode="success")
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k1"
        )
        db.commit()

        result = outbox_worker_service.run_once(settings=settings)
        assert result.claimed >= 1
        assert result.delivered >= 1

        row = db.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).first()
        assert row.status == OutboxEventStatus.DELIVERED
        assert row.delivered_at is not None

        attempts = db.scalars(
            select(IntegrationDeliveryAttempt).where(IntegrationDeliveryAttempt.outbox_event_id == row.id)
        ).all()
        assert len(attempts) == 1
        assert attempts[0].status == DeliveryAttemptStatus.SUCCESS

        db.refresh(connection)
        assert connection.status == IntegrationConnectionStatus.VERIFIED
        assert connection.failure_count == 0

    def test_promotes_a_failing_connection_back_to_verified_on_success(self, db, cleanup):
        tenant, connection = _make_tenant_and_connection(db, mode="success", status=IntegrationConnectionStatus.FAILING)
        connection.failure_count = 5
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k2"
        )
        db.commit()

        outbox_worker_service.run_once(settings=settings)

        db.refresh(connection)
        assert connection.status == IntegrationConnectionStatus.VERIFIED
        assert connection.failure_count == 0


class TestFailureAndDeadLetter:
    def test_retryable_failure_reschedules_with_backoff(self, db, cleanup):
        tenant, connection = _make_tenant_and_connection(db, mode="failure")
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k3"
        )
        db.commit()

        result = outbox_worker_service.run_once(settings=settings)
        assert result.retried == 1

        row = db.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).first()
        assert row.status == OutboxEventStatus.PENDING
        assert row.attempt_count == 1
        assert row.available_at > datetime.now(UTC) - timedelta(seconds=1)
        assert row.last_error

    def test_exhausting_max_attempts_dead_letters(self, db, cleanup):
        """Starts CONFIGURED (never yet verified) and stays CONFIGURED even
        after every attempt fails — FAILING specifically means "was
        VERIFIED, then regressed" (see IntegrationConnectionStatus's
        docstring); a connector that has never once succeeded has nothing
        to regress from, so CONFIGURED remains the accurate status."""
        tenant, connection = _make_tenant_and_connection(db, mode="failure")
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k4"
        )
        db.commit()

        for _ in range(settings.integration_max_delivery_attempts):
            outbox_worker_service.run_once(settings=settings)
            db.execute(
                text("UPDATE integration_outbox_events SET available_at = now() WHERE connection_id = :cid"),
                {"cid": str(connection.id)},
            )
            db.commit()

        row = db.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).first()
        assert row.status == OutboxEventStatus.DEAD_LETTER
        assert row.attempt_count == settings.integration_max_delivery_attempts

        db.refresh(connection)
        assert connection.status == IntegrationConnectionStatus.CONFIGURED
        assert connection.failure_count == settings.integration_max_delivery_attempts

    def test_a_previously_verified_connection_is_demoted_to_failing(self, db, cleanup):
        tenant, connection = _make_tenant_and_connection(
            db, mode="failure", status=IntegrationConnectionStatus.VERIFIED
        )
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k4b"
        )
        db.commit()

        for _ in range(3):
            outbox_worker_service.run_once(settings=settings)
            db.execute(
                text("UPDATE integration_outbox_events SET available_at = now() WHERE connection_id = :cid"),
                {"cid": str(connection.id)},
            )
            db.commit()

        db.refresh(connection)
        assert connection.status == IntegrationConnectionStatus.FAILING
        assert connection.failure_count == 3

    def test_permanent_failure_dead_letters_on_first_attempt(self, db, cleanup):
        tenant, connection = _make_tenant_and_connection(db, mode="permanent_failure")
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k5"
        )
        db.commit()

        result = outbox_worker_service.run_once(settings=settings)
        assert result.dead_lettered == 1

        row = db.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).first()
        assert row.status == OutboxEventStatus.DEAD_LETTER
        assert row.attempt_count == 1


class TestDeadLetterReplay:
    def test_replay_requeues_a_dead_lettered_row(self, db, cleanup):
        tenant, connection = _make_tenant_and_connection(db, mode="permanent_failure")
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k6"
        )
        db.commit()
        outbox_worker_service.run_once(settings=settings)

        row = db.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).first()
        assert row.status == OutboxEventStatus.DEAD_LETTER

        from app.repositories.integration import IntegrationOutboxEventRepository

        repo = IntegrationOutboxEventRepository(db)
        replayed = repo.replay_dead_letter(tenant_id=tenant.id, event_id=row.id)
        db.commit()
        assert replayed is True

        db.refresh(row)
        assert row.status == OutboxEventStatus.PENDING
        assert row.dead_lettered_at is None

    def test_replay_refuses_a_row_that_is_not_dead_lettered(self, db, cleanup):
        tenant, connection = _make_tenant_and_connection(db, mode="success")
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k7"
        )
        db.commit()

        row = db.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).first()

        from app.repositories.integration import IntegrationOutboxEventRepository

        repo = IntegrationOutboxEventRepository(db)
        replayed = repo.replay_dead_letter(tenant_id=tenant.id, event_id=row.id)
        assert replayed is False

    def test_replay_refuses_a_different_tenants_row(self, db, cleanup):
        tenant, connection = _make_tenant_and_connection(db, mode="permanent_failure")
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="k8"
        )
        db.commit()
        outbox_worker_service.run_once(settings=settings)

        row = db.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).first()

        from app.repositories.integration import IntegrationOutboxEventRepository

        repo = IntegrationOutboxEventRepository(db)
        replayed = repo.replay_dead_letter(tenant_id=uuid.uuid4(), event_id=row.id)
        assert replayed is False


# No test exercises the worker's "connection was deleted between claim and
# delivery" branch against a real committed row: integration_outbox_events
# has ON DELETE CASCADE on connection_id (see the migration and
# app/models/integration.py), so deleting a connection deletes every one
# of its outbox rows in the same statement — an outbox row can never
# outlive the connection it points at. The `connection is None` branch in
# app/services/outbox_worker_service.py::_deliver_one is deliberate
# defense in depth (e.g. against a future schema change that relaxes the
# FK), not a reachable production scenario today.


class TestConcurrentClaiming:
    def test_two_workers_never_claim_the_same_row(self, db, cleanup, executor):
        """The core FOR UPDATE SKIP LOCKED guarantee, exercised with real
        separate connections (each `run_once` call opens its own via
        `session_scope`) — not just two calls on one already-serialized
        session, which would prove nothing about the SKIP LOCKED clause."""
        tenant, connection = _make_tenant_and_connection(db, mode="success")
        cleanup.append(str(tenant.id))
        for i in range(10):
            outbox_producer_service.produce_event(
                db,
                tenant_id=tenant.id,
                event_type=EventType.CONTACT_CAPTURED,
                payload=_contact_payload(),
                dedup_key=f"concurrent-{i}",
            )
        db.commit()

        future_a = executor.submit(outbox_worker_service.claim_batch, settings=settings, worker_id="worker-a")
        future_b = executor.submit(outbox_worker_service.claim_batch, settings=settings, worker_id="worker-b")
        claimed_a = future_a.result(timeout=10)
        claimed_b = future_b.result(timeout=10)

        ids_a = {item.id for item in claimed_a}
        ids_b = {item.id for item in claimed_b}
        assert ids_a.isdisjoint(ids_b), "the same outbox row was claimed by both workers"
        assert len(ids_a) + len(ids_b) == 10

    def test_no_idle_in_transaction_or_held_locks_after_a_run(self, db, cleanup, multiconn_engine):
        tenant, connection = _make_tenant_and_connection(db, mode="success")
        cleanup.append(str(tenant.id))
        outbox_producer_service.produce_event(
            db,
            tenant_id=tenant.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=_contact_payload(),
            dedup_key="k10",
        )
        db.commit()

        outbox_worker_service.run_once(settings=settings)

        assert idle_in_transaction_count(multiconn_engine) == 0
        assert held_locks_on(multiconn_engine, table="integration_outbox_events") == 0


class TestScopedClaiming:
    """The dashboard's authenticated "process now" action and the
    integration lab both need to process only THEIR OWN tenant's backlog
    — never another tenant's, even though the underlying claim query has
    to look across the whole table's due rows to find them. This proves
    the tenant_id/connection_id scoping actually excludes other tenants'
    (and other connections') rows, not just that it returns *some*
    subset."""

    def test_tenant_scoped_claim_never_claims_another_tenants_rows(self, db, cleanup):
        tenant_a, connection_a = _make_tenant_and_connection(db, mode="success")
        tenant_b, connection_b = _make_tenant_and_connection(db, mode="success")
        cleanup.append(str(tenant_a.id))
        cleanup.append(str(tenant_b.id))
        outbox_producer_service.produce_event(
            db, tenant_id=tenant_a.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="a1"
        )
        outbox_producer_service.produce_event(
            db, tenant_id=tenant_b.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="b1"
        )
        db.commit()

        claimed = outbox_worker_service.claim_batch(settings=settings, tenant_id=tenant_a.id, batch_size=10)

        assert len(claimed) == 1
        assert claimed[0].tenant_id == tenant_a.id

    def test_connection_scoped_claim_never_claims_another_connections_rows(self, db, cleanup):
        tenant, connection_a = _make_tenant_and_connection(db, mode="success")
        cleanup.append(str(tenant.id))
        # Deliberately NOT subscribed to contact.captured — produce_event
        # fans out to every subscribed connection, so an unsubscribed
        # sibling connection must end up with no row of its own at all,
        # proving the scope filter has something real to exclude.
        connection_b = IntegrationConnection(
            tenant_id=tenant.id,
            connector_type=IntegrationConnectorType.MOCK,
            name="Second Connection",
            status=IntegrationConnectionStatus.CONFIGURED,
            config={"mode": "success"},
            enabled_event_types=[],
        )
        db.add(connection_b)
        db.flush()

        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="dk"
        )
        db.commit()

        claimed = outbox_worker_service.claim_batch(
            settings=settings, tenant_id=tenant.id, connection_id=connection_b.id, batch_size=10
        )
        assert claimed == []

        claimed_a = outbox_worker_service.claim_batch(
            settings=settings, tenant_id=tenant.id, connection_id=connection_a.id, batch_size=10
        )
        assert len(claimed_a) == 1
        assert claimed_a[0].connection_id == connection_a.id

    def test_run_once_scoped_to_a_connection_delivers_only_that_connections_events(self, db, cleanup):
        tenant, connection_a = _make_tenant_and_connection(db, mode="success")
        cleanup.append(str(tenant.id))
        connection_b = IntegrationConnection(
            tenant_id=tenant.id,
            connector_type=IntegrationConnectorType.MOCK,
            name="Second Connection",
            status=IntegrationConnectionStatus.CONFIGURED,
            config={"mode": "success"},
            enabled_event_types=[],  # not subscribed — see the previous test's comment
        )
        db.add(connection_b)
        db.flush()

        outbox_producer_service.produce_event(
            db, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=_contact_payload(), dedup_key="dka"
        )
        db.commit()

        result = outbox_worker_service.run_once(settings=settings, tenant_id=tenant.id, connection_id=connection_b.id)
        assert result.claimed == 0
        assert result.delivered == 0

        result = outbox_worker_service.run_once(settings=settings, tenant_id=tenant.id, connection_id=connection_a.id)
        assert result.claimed == 1
        assert result.delivered == 1


class TestProcessPendingNowEndpoint:
    """The dashboard's POST .../process-pending route, exercised through
    a real HTTP call against real committed data — the only way to prove
    it, since outbox_worker_service always opens its own session_scope()
    that cannot see an uncommitted savepoint from tests/conftest.py's
    db_backed_client fixture."""

    def test_process_pending_delivers_a_real_committed_event(self, real_client, cleanup_tenants, multiconn_engine):
        from tests.integration.helpers import register_tenant

        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="processpending")

        created = real_client.post(
            f"/api/v1/tenants/{tenant_id}/integrations",
            headers=headers,
            json={
                "connector_type": "mock",
                "name": "Process Pending Test",
                "config": {"mode": "success"},
                "enabled_event_types": [],
            },
        )
        assert created.status_code == 201, created.text
        connection_id = created.json()["id"]

        test_event = real_client.post(
            f"/api/v1/tenants/{tenant_id}/integrations/{connection_id}/test-event", headers=headers
        )
        assert test_event.status_code == 200, test_event.text

        result = real_client.post(
            f"/api/v1/tenants/{tenant_id}/integrations/{connection_id}/process-pending", headers=headers
        )
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["claimed"] == 1
        assert body["delivered"] == 1

        detail = real_client.get(f"/api/v1/tenants/{tenant_id}/integrations/{connection_id}", headers=headers)
        assert detail.json()["status"] == "verified"

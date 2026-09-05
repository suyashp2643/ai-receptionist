"""Functional tests for the tenant-scoped integration health/metrics
endpoint — exact numerator/denominator/time-range behavior for every
metric, every warning condition, and cross-tenant isolation. Query-count
bounding lives in its own file:
tests/test_phase8_integration_health_performance.py."""

import uuid
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.core.security import create_access_token
from app.models.enums import (
    DeliveryAttemptStatus,
    IntegrationConnectionStatus,
    IntegrationConnectorType,
    OutboxEventStatus,
)
from app.models.integration import IntegrationConnection, IntegrationDeliveryAttempt, IntegrationOutboxEvent
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_member, make_tenant_with_owner, make_user

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def _make_connection(db: Session, tenant, **overrides) -> IntegrationConnection:
    defaults = dict(
        tenant_id=tenant.id,
        connector_type=IntegrationConnectorType.MOCK,
        name=f"Conn {uuid.uuid4().hex[:6]}",
        status=IntegrationConnectionStatus.CONFIGURED,
        config={"mode": "success"},
        enabled_event_types=[],
        failure_count=0,
    )
    defaults.update(overrides)
    connection = IntegrationConnection(**defaults)
    db.add(connection)
    db.flush()
    return connection


def _make_outbox_event(db: Session, tenant, connection, **overrides) -> IntegrationOutboxEvent:
    defaults = dict(
        tenant_id=tenant.id,
        connection_id=connection.id,
        event_id=uuid.uuid4(),
        event_type="connection.test_event",
        event_version=1,
        dedup_key=uuid.uuid4().hex,
        payload={},
        status=OutboxEventStatus.PENDING,
        attempt_count=0,
    )
    defaults.update(overrides)
    row = IntegrationOutboxEvent(**defaults)
    db.add(row)
    db.flush()
    return row


def _make_attempt(db: Session, tenant, connection, outbox_event, *, status, created_at, duration_ms=None):
    row = IntegrationDeliveryAttempt(
        tenant_id=tenant.id,
        connection_id=connection.id,
        outbox_event_id=outbox_event.id,
        attempt_number=1,
        status=status,
        http_status_code=200 if status == DeliveryAttemptStatus.SUCCESS else 500,
        duration_ms=duration_ms,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _get_health(client: TestClient, tenant_id, user, **params):
    return client.get(f"/api/v1/tenants/{tenant_id}/integrations/health", headers=_auth_headers(user), params=params)


class TestPermissions:
    def test_unauthenticated_gets_401(self, db_backed_client: TestClient, db_session: Session):
        tenant, _owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/integrations/health")
        assert response.status_code == 401

    def test_non_member_gets_404(self, db_backed_client: TestClient, db_session: Session):
        tenant, _owner, _ = make_tenant_with_owner(db_session)
        outsider = make_user(db_session)
        response = _get_health(db_backed_client, tenant.id, outsider)
        assert response.status_code == 404

    def test_member_can_read_health(self, db_backed_client: TestClient, db_session: Session):
        from app.models.enums import TenantMemberRole

        tenant, _owner, _ = make_tenant_with_owner(db_session)
        member = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)
        response = _get_health(db_backed_client, tenant.id, member)
        assert response.status_code == 200


class TestEmptyTenant:
    def test_a_tenant_with_no_integrations_reports_all_zero_or_null(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = _get_health(db_backed_client, tenant.id, owner)
        assert response.status_code == 200
        body = response.json()
        assert body["connections"] == {"active": 0, "paused": 0, "failing": 0, "disabled": 0, "total": 0}
        assert body["pending_events"] == 0
        assert body["retry_backlog"] == 0
        assert body["oldest_pending_age_seconds"] is None
        assert body["dead_letter_count"] == 0
        assert body["successful_deliveries"] == 0
        assert body["failed_deliveries"] == 0
        assert body["success_rate"] is None  # never a misleading 0
        assert body["latency"] == {"p50_ms": None, "p95_ms": None, "sample_size": 0}
        assert body["last_success_at"] is None
        assert body["last_failure_at"] is None
        assert body["warnings"] == []


class TestConnectionStatusBreakdown:
    def test_each_status_is_counted_in_its_own_bucket(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        _make_connection(db_session, tenant, status=IntegrationConnectionStatus.CONFIGURED)
        _make_connection(db_session, tenant, status=IntegrationConnectionStatus.VERIFIED)
        _make_connection(db_session, tenant, status=IntegrationConnectionStatus.PAUSED)
        _make_connection(db_session, tenant, status=IntegrationConnectionStatus.FAILING)
        _make_connection(db_session, tenant, status=IntegrationConnectionStatus.DISABLED)

        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert body["connections"] == {"active": 2, "paused": 1, "failing": 1, "disabled": 1, "total": 5}


class TestOutboxMetrics:
    def test_pending_events_and_oldest_pending_age(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        connection = _make_connection(db_session, tenant)
        old_available_at = datetime.now(UTC) - timedelta(minutes=90)
        _make_outbox_event(
            db_session, tenant, connection, status=OutboxEventStatus.PENDING, available_at=old_available_at
        )
        _make_outbox_event(
            db_session, tenant, connection, status=OutboxEventStatus.PENDING, available_at=datetime.now(UTC)
        )
        _make_outbox_event(db_session, tenant, connection, status=OutboxEventStatus.DELIVERED)

        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert body["pending_events"] == 2
        assert body["oldest_pending_age_seconds"] >= 5300  # ~90 minutes, generous lower bound
        assert any(w["code"] == "stale_backlog" for w in body["warnings"])

    def test_retry_backlog_only_counts_pending_rows_with_a_prior_attempt(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        connection = _make_connection(db_session, tenant)
        _make_outbox_event(db_session, tenant, connection, status=OutboxEventStatus.PENDING, attempt_count=0)
        _make_outbox_event(db_session, tenant, connection, status=OutboxEventStatus.PENDING, attempt_count=2)

        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert body["pending_events"] == 2
        assert body["retry_backlog"] == 1

    def test_dead_letter_count(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        connection = _make_connection(db_session, tenant)
        _make_outbox_event(db_session, tenant, connection, status=OutboxEventStatus.DEAD_LETTER)
        _make_outbox_event(db_session, tenant, connection, status=OutboxEventStatus.DEAD_LETTER)

        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert body["dead_letter_count"] == 2


class TestDeliveryMetricsAndWindowScoping:
    def test_success_rate_numerator_and_denominator(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        connection = _make_connection(db_session, tenant)
        event = _make_outbox_event(db_session, tenant, connection)
        now = datetime.now(UTC)
        _make_attempt(
            db_session, tenant, connection, event, status=DeliveryAttemptStatus.SUCCESS, created_at=now, duration_ms=100
        )
        _make_attempt(
            db_session, tenant, connection, event, status=DeliveryAttemptStatus.SUCCESS, created_at=now, duration_ms=200
        )
        _make_attempt(
            db_session, tenant, connection, event, status=DeliveryAttemptStatus.RETRYABLE_FAILURE, created_at=now
        )

        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert body["successful_deliveries"] == 2
        assert body["failed_deliveries"] == 1
        assert body["success_rate"] == 2 / 3

    def test_attempts_outside_the_window_are_excluded_from_counts_but_not_from_last_success(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        connection = _make_connection(db_session, tenant)
        event = _make_outbox_event(db_session, tenant, connection)
        old_time = datetime.now(UTC) - timedelta(hours=48)
        _make_attempt(
            db_session,
            tenant,
            connection,
            event,
            status=DeliveryAttemptStatus.SUCCESS,
            created_at=old_time,
            duration_ms=50,
        )

        body = _get_health(db_backed_client, tenant.id, owner, window_hours=24).json()
        assert body["successful_deliveries"] == 0
        assert body["success_rate"] is None
        # last_success_at is all-time, not window-bounded.
        assert body["last_success_at"] is not None

    def test_latency_percentiles_from_a_known_sample(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        connection = _make_connection(db_session, tenant)
        event = _make_outbox_event(db_session, tenant, connection)
        now = datetime.now(UTC)
        for duration in [100, 200, 300, 400, 500]:
            _make_attempt(
                db_session,
                tenant,
                connection,
                event,
                status=DeliveryAttemptStatus.SUCCESS,
                created_at=now,
                duration_ms=duration,
            )

        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert body["latency"]["sample_size"] == 5
        assert body["latency"]["p50_ms"] == 300
        assert body["latency"]["p95_ms"] == 500

    def test_last_success_and_last_failure_are_independent_all_time_maxima(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        connection = _make_connection(db_session, tenant)
        event = _make_outbox_event(db_session, tenant, connection)
        earlier = datetime.now(UTC) - timedelta(hours=2)
        later = datetime.now(UTC) - timedelta(minutes=5)
        _make_attempt(db_session, tenant, connection, event, status=DeliveryAttemptStatus.SUCCESS, created_at=earlier)
        _make_attempt(
            db_session, tenant, connection, event, status=DeliveryAttemptStatus.PERMANENT_FAILURE, created_at=later
        )

        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert body["last_success_at"] is not None
        assert body["last_failure_at"] is not None
        assert body["last_failure_at"] > body["last_success_at"]


class TestHealthWarnings:
    def test_repeated_failures_warning(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        _make_connection(db_session, tenant, failure_count=5)
        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert any(w["code"] == "repeated_failures" for w in body["warnings"])

    def test_disabled_connector_warning(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        _make_connection(db_session, tenant, status=IntegrationConnectionStatus.DISABLED)
        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert any(w["code"] == "disabled_connector" for w in body["warnings"])

    def test_missing_encryption_configuration_warning(self, db_backed_client: TestClient, db_session: Session):
        """Overrides the `get_settings` FastAPI dependency directly for
        this one request, rather than monkeypatching the module-level
        `get_settings()` LRU-cached singleton — tests/test_health.py calls
        `get_settings.cache_clear()`, which (depending on suite run order)
        can silently replace that singleton with a fresh instance the
        monkeypatch never touched, making the mutation invisible to the
        route. Overriding the dependency is immune to that regardless of
        test order."""
        from app.config import get_settings as get_settings_dependency

        tenant, owner, _ = make_tenant_with_owner(db_session)
        _make_connection(
            db_session,
            tenant,
            signing_secret_ciphertext="gAAAAA-fake-ciphertext-value",
            signing_secret_key_version=1,
        )
        no_key_settings = get_settings_dependency().model_copy(update={"integration_encryption_key": None})
        app = db_backed_client.app
        app.dependency_overrides[get_settings_dependency] = lambda: no_key_settings
        try:
            body = _get_health(db_backed_client, tenant.id, owner).json()
            assert any(w["code"] == "missing_encryption_configuration" for w in body["warnings"])
        finally:
            del app.dependency_overrides[get_settings_dependency]

    def test_unsupported_key_version_warning(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        _make_connection(
            db_session,
            tenant,
            signing_secret_ciphertext="gAAAAA-fake-ciphertext-value",
            signing_secret_key_version=999,
        )
        body = _get_health(db_backed_client, tenant.id, owner).json()
        assert any(w["code"] == "unsupported_key_version" for w in body["warnings"])


class TestCrossTenantIsolation:
    def test_another_tenants_data_never_appears(self, db_backed_client: TestClient, db_session: Session):
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        connection_b = _make_connection(
            db_session, tenant_b, status=IntegrationConnectionStatus.FAILING, failure_count=10
        )
        event_b = _make_outbox_event(db_session, tenant_b, connection_b, status=OutboxEventStatus.DEAD_LETTER)
        _make_attempt(
            db_session,
            tenant_b,
            connection_b,
            event_b,
            status=DeliveryAttemptStatus.SUCCESS,
            created_at=datetime.now(UTC),
        )

        body = _get_health(db_backed_client, tenant_a.id, owner_a).json()
        assert body["connections"]["total"] == 0
        assert body["dead_letter_count"] == 0
        assert body["successful_deliveries"] == 0
        assert body["warnings"] == []

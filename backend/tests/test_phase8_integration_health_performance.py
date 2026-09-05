"""Query-count regression test for the integration health endpoint,
matching the existing convention in tests/test_dashboard_performance.py:
seed a meaningful volume and assert the endpoint's SQL statement count
stays bounded regardless of it — an N+1 regression would instead make the
count grow with SEED_CONNECTION_COUNT / SEED_ATTEMPT_COUNT.

Exact count observed at the time this test was written (see the assert
message if it ever changes): 8 SQL statements — auth/tenant-context
resolution (2: user lookup, membership lookup) + the health service's own
6 queries (connection rows; outbox status GROUP BY; pending-backlog
aggregate; delivery window aggregate; duration sample; last-success/
last-failure aggregate). Asserted with headroom (< 15) rather than
pinned to exactly 8, so an incidental, harmless ORM change doesn't turn
into pointless test churn — the property this test actually guards is
"bounded", not "exactly this literal number forever".
"""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

from app.config import get_settings
from app.core.security import create_access_token
from app.models.enums import DeliveryAttemptStatus, IntegrationConnectorType, OutboxEventStatus
from app.models.integration import IntegrationConnection, IntegrationDeliveryAttempt, IntegrationOutboxEvent
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from tests.factories import make_tenant_with_owner

settings = get_settings()

SEED_CONNECTION_COUNT = 15
SEED_ATTEMPT_COUNT = 60


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def count_queries(session: Session):
    counter = {"count": 0}
    connection = session.connection()

    def _on_execute(*_args, **_kwargs):
        counter["count"] += 1

    event.listen(connection, "before_cursor_execute", _on_execute)
    try:
        yield counter
    finally:
        event.remove(connection, "before_cursor_execute", _on_execute)


def _seed(db: Session, *, tenant, connection_count: int, attempt_count: int) -> None:
    connections = []
    for i in range(connection_count):
        connection = IntegrationConnection(
            tenant_id=tenant.id,
            connector_type=IntegrationConnectorType.MOCK,
            name=f"Perf Conn {i}",
            config={"mode": "success"},
            enabled_event_types=[],
        )
        db.add(connection)
        connections.append(connection)
    db.flush()

    for i in range(attempt_count):
        connection = connections[i % len(connections)]
        outbox_event = IntegrationOutboxEvent(
            tenant_id=tenant.id,
            connection_id=connection.id,
            event_id=uuid.uuid4(),
            event_type="connection.test_event",
            event_version=1,
            dedup_key=uuid.uuid4().hex,
            payload={},
            status=OutboxEventStatus.DELIVERED if i % 3 else OutboxEventStatus.PENDING,
        )
        db.add(outbox_event)
        db.flush()
        db.add(
            IntegrationDeliveryAttempt(
                tenant_id=tenant.id,
                connection_id=connection.id,
                outbox_event_id=outbox_event.id,
                attempt_number=1,
                status=DeliveryAttemptStatus.SUCCESS if i % 2 else DeliveryAttemptStatus.RETRYABLE_FAILURE,
                duration_ms=100 + i,
                created_at=datetime.now(UTC),
            )
        )
    db.flush()


class TestNoQueryCountRegression:
    def test_health_endpoint_query_count_is_bounded(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        _seed(db_session, tenant=tenant, connection_count=SEED_CONNECTION_COUNT, attempt_count=SEED_ATTEMPT_COUNT)
        db_session.commit()

        with count_queries(db_session) as counter:
            response = db_backed_client.get(
                f"/api/v1/tenants/{tenant.id}/integrations/health", headers=_auth_headers(owner)
            )
        assert response.status_code == 200
        assert response.json()["connections"]["total"] == SEED_CONNECTION_COUNT
        message = (
            f"health endpoint issued {counter['count']} queries for "
            f"{SEED_CONNECTION_COUNT} connections / {SEED_ATTEMPT_COUNT} attempts"
        )
        assert counter["count"] < 15, message

    def test_query_count_does_not_grow_with_seeded_volume(self, db_backed_client: TestClient, db_session: Session):
        """The real N+1 guard: run the endpoint against a SMALL seed and a
        LARGE seed and assert the query count is identical — not just
        "under some ceiling," which a coincidentally-small ceiling could
        pass even with a mild per-row regression."""
        tenant_small, owner_small, _ = make_tenant_with_owner(db_session, tenant_name="Small")
        _seed(db_session, tenant=tenant_small, connection_count=2, attempt_count=4)
        db_session.commit()
        with count_queries(db_session) as small_counter:
            response_small = db_backed_client.get(
                f"/api/v1/tenants/{tenant_small.id}/integrations/health", headers=_auth_headers(owner_small)
            )
        assert response_small.status_code == 200

        tenant_large, owner_large, _ = make_tenant_with_owner(db_session, tenant_name="Large")
        _seed(db_session, tenant=tenant_large, connection_count=SEED_CONNECTION_COUNT, attempt_count=SEED_ATTEMPT_COUNT)
        db_session.commit()
        with count_queries(db_session) as large_counter:
            response_large = db_backed_client.get(
                f"/api/v1/tenants/{tenant_large.id}/integrations/health", headers=_auth_headers(owner_large)
            )
        assert response_large.status_code == 200

        assert small_counter["count"] == large_counter["count"], (
            f"small-seed query count ({small_counter['count']}) differs from "
            f"large-seed query count ({large_counter['count']}) — query count must not scale with data volume"
        )

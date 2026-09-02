"""Fixtures for PostgreSQL multi-connection integration tests.

Deliberately independent of `tests/conftest.py`'s `db_backed_client` /
`db_session` fixtures: those intentionally share ONE SQLAlchemy session
across every request in a test (for fast, rolled-back-at-the-end isolation)
— exactly the pattern that collapsed production's several independently
pooled connections into one and masked the Phase 4 concurrency bugs this
package exists to catch. Every fixture here instead drives the app through
its REAL, unmodified `get_db` dependency, so each HTTP call gets a
genuinely fresh `Session` bound to a freshly checked-out connection from
the real connection pool — exactly like production.

Because these tests commit real rows to the real database (there is no
rollback safety net), every test that creates a tenant MUST register its
own tenant id with the `cleanup_tenants` fixture, which deletes exactly
those rows (and only those rows, cascading through the standard
`ON DELETE CASCADE` foreign keys) once the test finishes — pass or fail —
after re-verifying the database name.
"""

import pytest
from app.db.session import get_engine
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import text

APPROVED_TEST_DATABASE_NAME = "ai_receptionist_dev"


def _assert_approved_database(engine) -> None:
    if engine.url.database != APPROVED_TEST_DATABASE_NAME:
        pytest.fail(
            f"Refusing to touch database {engine.url.database!r}; "
            f"multi-connection integration tests only ever run against "
            f"{APPROVED_TEST_DATABASE_NAME!r}."
        )


@pytest.fixture(scope="session")
def multiconn_engine():
    """The application's own engine/connection pool — reused as-is (not a
    second engine) so pool introspection in these tests reflects exactly
    what the app under test is doing, not a separate observer's pool."""
    engine = get_engine()
    if engine is None:
        pytest.skip("DATABASE_URL is not configured; skipping multi-connection integration tests.")
    _assert_approved_database(engine)
    return engine


@pytest.fixture()
def real_client(multiconn_engine):
    """A `TestClient` with NO dependency override — every request resolves
    the real `app.db.session.get_db`, i.e. a fresh `Session` on a freshly
    checked-out pooled connection per request, identical to production.
    This is what makes cross-request lock contention and connection-pool
    behavior observable at all; `db_backed_client` cannot reproduce either."""
    app = create_app()
    with TestClient(app) as client:
        yield client


class CreatedTestData:
    """Tracks exactly what one test created, so `cleanup_tenants` deletes
    exactly that and nothing else."""

    def __init__(self) -> None:
        self.tenant_ids: list[str] = []
        self.user_ids: list[str] = []


@pytest.fixture()
def cleanup_tenants(multiconn_engine):
    """Yields a `CreatedTestData` a test appends its own created tenant and
    user ids to. Deletes exactly those tenants (cascading to every
    tenant-owned row, including conversations/messages/summaries) and then
    the user accounts that owned them, after the test — even on failure —
    never a broader delete/truncate. Re-verifies the database name
    immediately before deleting, not just at fixture setup.

    Tenants and users are two separate deletes because `ON DELETE CASCADE`
    only runs from `tenants` down to tenant-owned rows (including
    `tenant_members`) — a `User` is never owned by a tenant (one user can
    belong to several), so deleting a tenant alone leaves the user account
    it registered behind."""
    created = CreatedTestData()
    yield created
    if not created.tenant_ids and not created.user_ids:
        return
    _assert_approved_database(multiconn_engine)
    with multiconn_engine.begin() as conn:
        if created.tenant_ids:
            conn.execute(text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": created.tenant_ids})
        if created.user_ids:
            conn.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": created.user_ids})


def idle_in_transaction_count(engine) -> int:
    """Observable, non-implementation-internal signal for 'is any
    connection holding an open transaction right now' — the exact
    `pg_stat_activity` state that revealed both the held-lock and the
    leaked-connection bugs during live testing. Excludes this test
    process's own backend pid so checking from a fresh connection (which
    briefly exists in 'idle', never 'idle in transaction') never
    self-counts."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE state = 'idle in transaction' AND pid <> pg_backend_pid()"
            )
        ).scalar()


def held_locks_on(engine, *, table: str) -> int:
    """Counts locks currently held on `table` by any *other* backend —
    a direct, observable check for 'is something still holding the
    conversation row lock', independent of transaction *state* text."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM pg_locks l "
                "JOIN pg_class c ON l.relation = c.oid "
                "WHERE c.relname = :table AND l.pid <> pg_backend_pid() AND l.granted"
            ),
            {"table": table},
        ).scalar()

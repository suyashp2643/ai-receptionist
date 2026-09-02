from contextlib import contextmanager

import pytest
from app.api.deps import get_db as api_get_db
from app.api.deps import get_session_scope_factory as api_get_session_scope_factory
from app.db.session import get_engine
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

# The only database Phase 2 DB-backed tests are ever allowed to touch. If
# DATABASE_URL points somewhere else, tests refuse to run rather than risk
# operating on (or, in later phases, cleaning up) an unrelated database.
APPROVED_TEST_DATABASE_NAME = "ai_receptionist_dev"


@pytest.fixture()
def client() -> TestClient:
    """Phase 1 fixture, unchanged: a plain app instance with no database
    dependency override. Health endpoints must keep working without a
    database, so this fixture must never be made to require one."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(scope="session")
def _db_engine():
    engine = get_engine()
    if engine is None:
        pytest.skip("DATABASE_URL is not configured; skipping database-backed tests.")
    if engine.url.database != APPROVED_TEST_DATABASE_NAME:
        pytest.fail(
            f"Refusing to run database-backed tests against database "
            f"{engine.url.database!r}; expected {APPROVED_TEST_DATABASE_NAME!r}."
        )
    return engine


@pytest.fixture()
def db_session(_db_engine) -> Session:
    """One test = one outer transaction that is always rolled back at the end.

    Application code (via the real app.db.session.get_db semantics, mirrored
    in the dependency override below) still calls session.commit()/rollback()
    per request — join_transaction_mode="create_savepoint" means those calls
    only manage a SAVEPOINT nested inside this outer transaction, so request
    atomicity is still genuinely exercised, but nothing this test does is
    ever visible to any other test or left behind in the database.
    """
    connection = _db_engine.connect()
    outer_transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = session_factory()

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()


@pytest.fixture()
def db_backed_client(db_session: Session) -> TestClient:
    """Phase 2 fixture for auth/tenant tests: same app, but every request's
    `get_db` dependency resolves to this test's isolated, rolled-back-at-the-end
    session instead of a fresh real one."""

    def override_get_db():
        # `db_session`'s own sessionmaker already uses
        # join_transaction_mode="create_savepoint" (see its docstring
        # above) — that alone makes session.commit()/rollback() manage a
        # SAVEPOINT nested inside the test's outer transaction, exactly
        # mirroring real app.db.session.get_db semantics. Wrapping this in
        # an *additional* manual `db_session.begin_nested()` here used to
        # double-nest savepoints: application code calling `.commit()`
        # while still lexically inside that extra `with` block raised
        # "Can't operate on closed transaction inside context manager" as
        # soon as the session was touched again (e.g. a StreamingResponse
        # generator's phased commits) — a bug in the fixture, not a
        # reason for application code to avoid committing.
        yield db_session

    @contextmanager
    def override_session_scope():
        """Test-only substitute for `app.db.session.session_scope`, used by
        the streaming test-conversation route (see
        `app/api/v1/conversations.py` and `get_session_scope_factory` in
        `app/api/deps.py`). Owns and cleans up its own session
        independently of production's `session_scope`: it applies the same
        commit-on-success/rollback-on-failure contract, but against this
        test's single shared, savepoint-joined `db_session` rather than
        creating a new one — and it deliberately never calls `.close()`.
        `db_session` is owned by the `db_session` fixture above, which
        closes it in its own teardown exactly once, after every request in
        this test (streaming or not) has run; closing it again here,
        mid-test, would detach every ORM object the test (or an earlier
        request in the same test) still holds — for no benefit `commit()`/
        `rollback()` don't already provide, since they alone are what makes
        each request's savepoint atomic. Production's own `session_scope`
        is untouched by this and always closes; this override exists
        specifically so the test suite's need to share one session across
        a test's requests doesn't require weakening that production
        contract."""
        try:
            yield db_session
            db_session.commit()
        except BaseException:
            db_session.rollback()
            raise

    app = create_app()
    app.dependency_overrides[api_get_db] = override_get_db
    app.dependency_overrides[api_get_session_scope_factory] = lambda: override_session_scope
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

import pytest
from app.api.deps import get_db as api_get_db
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
        # A per-request SAVEPOINT nested inside the test's own outer
        # savepoint (see db_session above). This mirrors the real
        # app.db.session.get_db commit/rollback-per-request semantics
        # WITHOUT touching the outer savepoint that holds this test's setup
        # data — committing/rolling back that one is reserved for the test
        # fixture's teardown only.
        with db_session.begin_nested():
            yield db_session

    app = create_app()
    app.dependency_overrides[api_get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

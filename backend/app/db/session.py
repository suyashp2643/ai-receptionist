from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine() -> Engine | None:
    """Lazily creates the SQLAlchemy engine. Returns None if DATABASE_URL is unset."""
    global _engine
    settings = get_settings()
    if not settings.database_url:
        return None
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
    return _engine


def get_session_factory() -> sessionmaker | None:
    global _session_factory
    engine = get_engine()
    if engine is None:
        return None
    if _session_factory is None:
        _session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _session_factory


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """The single, explicit ownership contract for a request-scoped
    session: create it here, commit it here on success, roll it back here
    on any failure, and — always, unconditionally — close it here,
    returning its connection to the pool. Nothing outside this function
    ever creates or closes a session it uses; every caller (`get_db` below,
    and any code needing a session outside FastAPI's own dependency
    exit-stack timing — see `app/api/v1/conversations.py`) borrows the
    session for the lifetime of its own `with`/`yield` block and nothing
    more.

    `except BaseException` (not `Exception`) deliberately also covers
    `GeneratorExit` — thrown in here if whoever is using this session is
    itself a generator that gets `.close()`d early (e.g. an SSE route whose
    client disconnects) — and `KeyboardInterrupt`/`SystemExit`: every one of
    these still needs the transaction rolled back and the connection
    returned before it propagates, not left for whatever cleans up
    eventually. The `finally: db.close()` is unconditional on top of that:
    even if `rollback()` itself somehow raised, the connection is still
    released. None of this depends on `__del__`, garbage collection,
    reference counting, or a pool timeout ever running — every exit path is
    an explicit call in this function.
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Database is not configured (DATABASE_URL is not set).")
    db = factory()
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped DB session — adapts
    `session_scope` (see its docstring for the actual ownership contract)
    to FastAPI's `Depends(..., yield)` protocol.

    For an ordinary (non-streaming) route, FastAPI closes this dependency's
    exit stack — running the code after this generator's `yield`, i.e.
    `session_scope`'s own commit-or-rollback-then-close — once the route
    handler function returns, which is after all of that handler's own
    work is done. **This does not hold for a route returning a
    `StreamingResponse`**: FastAPI's dependency exit stack closes as soon
    as the route function returns the `StreamingResponse` *object*, which
    happens before Starlette ever starts draining its body — i.e. before a
    streaming route's generator body has run at all. A route that needs a
    session for work happening *inside* its streamed generator must not
    rely on this dependency for that part; it must hold its own
    `session_scope()` open for the generator's entire lifetime instead —
    see `app/api/v1/conversations.py`'s `send_test_message` for the pattern,
    and `get_session_scope_factory` in `app/api/deps.py` for how tests
    substitute their own session there.
    """
    with session_scope() as db:
        yield db


def check_database_connection() -> dict[str, str]:
    """Reports DB reachability without raising — used by health endpoints.

    Distinguishes "not configured" (no DATABASE_URL yet, expected in early
    Phase 1 setups) from "unavailable" (configured but unreachable).
    """
    settings = get_settings()
    if not settings.database_url:
        return {"status": "not_configured", "detail": "DATABASE_URL is not set"}

    engine = get_engine()
    assert engine is not None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "detail": "connected"}
    except SQLAlchemyError as exc:
        return {"status": "unavailable", "detail": exc.__class__.__name__}

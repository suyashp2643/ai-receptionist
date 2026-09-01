from collections.abc import Generator

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


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped DB session.

    Commits once, only if the request handler completes without raising —
    this is what makes multi-step operations like registration (create user +
    tenant + membership) atomic: any exception anywhere in the request rolls
    back everything, since nothing was committed yet.
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Database is not configured (DATABASE_URL is not set).")
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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

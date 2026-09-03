"""Shared optimistic-concurrency helper for Phase 6's status-update
endpoints (enquiries, appointment requests, human handoffs). Every status
change a dashboard user makes must supply the `version` it read; a stale
`version` means someone else already wrote first, and the caller must be
told to reload rather than silently overwriting that other write."""

from typing import Any, TypeVar

from sqlalchemy import update
from sqlalchemy.orm import DeclarativeBase, Session

ModelT = TypeVar("ModelT", bound=DeclarativeBase)


class VersionConflictError(Exception):
    """Raised when the row's current `version` no longer matches the
    version the caller last read — the API layer turns this into a 409."""


def apply_versioned_update(db: Session, obj: ModelT, *, expected_version: int, values: dict[str, Any]) -> None:
    """Applies `values` (never including `version` itself) to `obj` via a
    single conditional UPDATE gated on `id`, `tenant_id`, and
    `version == expected_version`, incrementing `version` atomically in the
    same statement. On success, refreshes `obj` in place so the caller can
    serialize it immediately without a second query. Raises
    VersionConflictError, and leaves `obj` untouched, if no row matched —
    this covers both a genuine concurrent write and the resource having
    vanished, since either way there is nothing safe to overwrite."""
    model = type(obj)
    stmt = (
        update(model)
        .where(
            model.id == obj.id,  # type: ignore[attr-defined]
            model.tenant_id == obj.tenant_id,  # type: ignore[attr-defined]
            model.version == expected_version,  # type: ignore[attr-defined]
        )
        .values(**values, version=model.version + 1)  # type: ignore[attr-defined]
    )
    result = db.execute(stmt)
    if result.rowcount != 1:
        raise VersionConflictError("This record was changed by someone else. Reload and try again.")
    db.refresh(obj)

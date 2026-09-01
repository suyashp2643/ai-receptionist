#!/usr/bin/env python3
"""Seeds the global industry-template catalog. Safe to run any number of
times — see app.seed_data.seed_runner.seed_industry_templates for the
idempotency guarantee (existing (key, version) rows are never touched).

Usage:
    .venv/bin/python scripts/seed_industry_templates.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import get_session_factory  # noqa: E402
from app.seed_data.seed_runner import seed_industry_templates  # noqa: E402


def main() -> int:
    session_factory = get_session_factory()
    if session_factory is None:
        print("DATABASE_URL is not configured — cannot seed.", file=sys.stderr)
        return 1

    db = session_factory()
    try:
        result = seed_industry_templates(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"Created {len(result.created)} template(s): {result.created}")
    print(f"Skipped {len(result.skipped)} already-seeded template(s): {result.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

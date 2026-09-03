#!/usr/bin/env python3
"""DEVELOPMENT-ONLY seed for the Phase 7 public marketing-site demos: three
clearly-fictional tenants (clinic, hotel, real estate), each with an ACTIVE
receptionist and an ACTIVE widget installation at a fixed public_id — no
user, no password, no tenant_member (see app/seed_data/public_demo_tenants.py
for why). Idempotent — re-running skips any demo tenant whose fixed slug
already exists. Never run in production.

Usage:
    .venv/bin/python scripts/seed_public_demos.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.seed_data.public_demo_tenants import seed_public_demo_tenants  # noqa: E402
from app.seed_data.seed_runner import seed_industry_templates  # noqa: E402


def main() -> int:
    settings = get_settings()
    if settings.environment != "development":
        print(
            f"Refusing to run: ENVIRONMENT is {settings.environment!r}, not 'development'. "
            "This seed creates fictional public-demo tenants and must never run outside local development.",
            file=sys.stderr,
        )
        return 1

    session_factory = get_session_factory()
    if session_factory is None:
        print("DATABASE_URL is not configured — cannot seed.", file=sys.stderr)
        return 1

    db = session_factory()
    try:
        seed_industry_templates(db)  # the demo tenants need the catalog to exist
        result = seed_public_demo_tenants(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"Created {len(result.created)} public demo tenant(s): {result.created}")
    print(f"Skipped {len(result.skipped)} already-seeded public demo tenant(s): {result.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

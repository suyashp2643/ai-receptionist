#!/usr/bin/env python3
"""DEVELOPMENT-ONLY demo seed: creates 3 clearly-fictional demo tenants
(real estate agency, dental clinic, boutique hotel) for manually exploring
the onboarding flow and dashboard. Never run this in production.

Idempotent — re-running skips any demo tenant whose fixed email already
exists. Generates a fresh random password per demo user each time it
actually creates one, and prints it ONCE here — it is never stored in any
file, tracked document, or database column in plaintext.

Usage:
    .venv/bin/python scripts/seed_demo_data.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.seed_data.demo_tenants import seed_demo_tenants  # noqa: E402
from app.seed_data.seed_runner import seed_industry_templates  # noqa: E402


def main() -> int:
    settings = get_settings()
    if settings.environment != "development":
        print(
            f"Refusing to run: ENVIRONMENT is {settings.environment!r}, not 'development'. "
            "This seed creates fictional demo accounts and must never run outside local development.",
            file=sys.stderr,
        )
        return 1

    session_factory = get_session_factory()
    if session_factory is None:
        print("DATABASE_URL is not configured — cannot seed.", file=sys.stderr)
        return 1

    db = session_factory()
    try:
        seed_industry_templates(db)  # demo tenants need the catalog to exist
        result = seed_demo_tenants(db, settings)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"Created {len(result.created)} demo tenant(s): {result.created}")
    print(f"Skipped {len(result.skipped)} already-seeded demo tenant(s): {result.skipped}")
    if result.generated_credentials:
        print("\nOne-time demo credentials (not stored anywhere — save them now):")
        for email, password in result.generated_credentials:
            print(f"  {email} / {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

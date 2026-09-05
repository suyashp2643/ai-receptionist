#!/usr/bin/env python3
"""Explicit, operator-triggered stale-conversation sweep. NOT a
scheduler — this process runs once and exits; nothing in this codebase
invokes it automatically. Run it by hand, from an external cron entry, or
from a future phase's own scheduler — that decision is deliberately left
outside this phase's scope.

Marks each ACTIVE conversation whose last activity is older than
`--stale-after-minutes` as ABANDONED and produces a `conversation.abandoned`
Phase 8 event for every tenant connection subscribed to it.

Usage:
    .venv/bin/python scripts/sweep_stale_conversations.py --stale-after-minutes 60
    .venv/bin/python scripts/sweep_stale_conversations.py --tenant-id <uuid> --batch-limit 50
"""

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import get_engine, session_scope  # noqa: E402
from app.services.conversation_sweep_service import DEFAULT_STALE_AFTER_MINUTES, sweep_stale_conversations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stale-after-minutes", type=int, default=DEFAULT_STALE_AFTER_MINUTES)
    parser.add_argument("--batch-limit", type=int, default=100, help="Max conversations to sweep in this one run.")
    parser.add_argument("--tenant-id", type=uuid.UUID, default=None, help="Limit to one tenant; default is all.")
    args = parser.parse_args()

    if get_engine() is None:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return 1

    with session_scope() as db:
        result = sweep_stale_conversations(
            db,
            stale_after_minutes=args.stale_after_minutes,
            batch_limit=args.batch_limit,
            tenant_id=args.tenant_id,
        )
    print(f"scanned={result.scanned} abandoned={result.abandoned}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

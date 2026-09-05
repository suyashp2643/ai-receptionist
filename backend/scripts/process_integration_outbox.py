#!/usr/bin/env python3
"""Phase 8 outbox delivery CLI — the zero-paid-infrastructure alternative
to a message-broker worker. Every subcommand opens its own real DB
sessions via app.db.session.session_scope (through
app.services.outbox_worker_service) — nothing here holds a session open
across the whole process; each claim/deliver/record cycle is
self-contained, exactly as it is when triggered any other way.

Never prints a payload body, a signing secret, or a raw API key — `status`
and `process-once`/`loop` report only counts and safe summary fields.

Usage:
    .venv/bin/python scripts/process_integration_outbox.py status
    .venv/bin/python scripts/process_integration_outbox.py process-once
    .venv/bin/python scripts/process_integration_outbox.py loop --max-iterations 20 --poll-interval-seconds 2
    .venv/bin/python scripts/process_integration_outbox.py retry-dead-letter --tenant-id <uuid> --event-id <uuid>
"""

import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.session import get_engine, session_scope  # noqa: E402
from app.repositories.integration import IntegrationOutboxEventRepository  # noqa: E402
from app.services import integration_connection_service, outbox_worker_service  # noqa: E402


def _require_database() -> None:
    if get_engine() is None:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        sys.exit(1)


def cmd_status(_args: argparse.Namespace) -> int:
    with session_scope() as db:
        counts = IntegrationOutboxEventRepository(db).count_by_status()
    for status_name in ("pending", "claimed", "delivered", "dead_letter"):
        print(f"{status_name:12s} {counts.get(status_name, 0)}")
    return 0


def cmd_process_once(_args: argparse.Namespace) -> int:
    settings = get_settings()
    result = outbox_worker_service.run_once(settings=settings)
    print(
        f"claimed={result.claimed} delivered={result.delivered} retried={result.retried} "
        f"dead_lettered={result.dead_lettered}"
    )
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    settings = get_settings()
    iterations = 0
    while args.max_iterations is None or iterations < args.max_iterations:
        result = outbox_worker_service.run_once(settings=settings)
        print(
            f"[{iterations}] claimed={result.claimed} delivered={result.delivered} "
            f"retried={result.retried} dead_lettered={result.dead_lettered}"
        )
        iterations += 1
        if args.max_iterations is not None and iterations >= args.max_iterations:
            break
        time.sleep(args.poll_interval_seconds)
    return 0


def cmd_retry_dead_letter(args: argparse.Namespace) -> int:
    with session_scope() as db:
        replayed = integration_connection_service.replay_dead_letter(
            db, tenant_id=args.tenant_id, actor_user_id=args.actor_user_id, event_id=args.event_id
        )
    print("replayed" if replayed else "not eligible (not found, wrong tenant, or not dead-lettered)")
    return 0 if replayed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Print outbox row counts by status.")
    subparsers.add_parser("process-once", help="Claim and attempt delivery for one batch, then exit.")

    loop_parser = subparsers.add_parser("loop", help="Repeatedly process batches in this process.")
    loop_parser.add_argument("--max-iterations", type=int, default=None, help="Stop after this many iterations.")
    loop_parser.add_argument("--poll-interval-seconds", type=float, default=5.0)

    retry_parser = subparsers.add_parser("retry-dead-letter", help="Re-queue one dead-lettered delivery.")
    retry_parser.add_argument("--tenant-id", type=uuid.UUID, required=True, dest="tenant_id")
    retry_parser.add_argument("--event-id", type=uuid.UUID, required=True, dest="event_id")
    retry_parser.add_argument(
        "--actor-user-id",
        type=uuid.UUID,
        required=True,
        dest="actor_user_id",
        help="User id recorded on the activity event for this replay.",
    )

    args = parser.parse_args()
    _require_database()

    handlers = {
        "status": cmd_status,
        "process-once": cmd_process_once,
        "loop": cmd_loop,
        "retry-dead-letter": cmd_retry_dead_letter,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

"""Explicit, bounded stale-conversation sweep — the producer for the
Phase 8 `conversation.abandoned` event, which otherwise has a schema but
no writer (see docs/integration-contracts.md's Known Limitations before
this module existed).

Deliberately NOT a scheduler. Nothing in this codebase calls this
automatically — it runs only when explicitly invoked via
`scripts/sweep_stale_conversations.py`, matching this phase's "no
automatically running scheduler" constraint. A future phase's own
scheduler, an external cron entry, or an operator running the CLI by
hand are all valid callers; none of that is wired up here.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations import payload_builders
from app.integrations.envelope import EventType
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus
from app.repositories.conversation import ConversationMessageRepository
from app.services import outbox_producer_service

logger = logging.getLogger("app.services.conversation_sweep")

DEFAULT_STALE_AFTER_MINUTES = 60
# A hard ceiling independent of whatever a caller passes — one invocation's
# work is always finite regardless of backlog size, matching the same
# "bounded batch" discipline as the outbox worker's own claim size.
MAX_BATCH_LIMIT = 500


@dataclass
class SweepResult:
    scanned: int = 0
    abandoned: int = 0


def sweep_stale_conversations(
    db: Session,
    *,
    stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES,
    batch_limit: int = 100,
    tenant_id: uuid.UUID | None = None,
) -> SweepResult:
    """Finds ACTIVE conversations whose most recent activity
    (`last_message_at`, falling back to `started_at` for a conversation
    that never got a reply) is older than `stale_after_minutes`,
    transitions each to ABANDONED, and produces one
    `conversation.abandoned` outbox row per subscribed connection —
    exactly the same production call `complete_conversation` makes for
    `conversation.completed` (app/ai/orchestrator.py), just triggered by
    this explicit sweep instead of a user action. Never commits — the
    caller owns the transaction, same convention as every other service
    function in this codebase."""
    batch_limit = min(max(1, batch_limit), MAX_BATCH_LIMIT)
    cutoff = datetime.now(UTC) - timedelta(minutes=stale_after_minutes)

    conditions = [
        Conversation.status == ConversationStatus.ACTIVE,
        func.coalesce(Conversation.last_message_at, Conversation.started_at) < cutoff,
    ]
    if tenant_id is not None:
        conditions.append(Conversation.tenant_id == tenant_id)

    stmt = select(Conversation).where(*conditions).order_by(Conversation.started_at).limit(batch_limit)
    stale = db.scalars(stmt).all()

    result = SweepResult(scanned=len(stale))
    for conversation in stale:
        conversation.status = ConversationStatus.ABANDONED
        _, message_count = ConversationMessageRepository(db, conversation.tenant_id).list_for_conversation(
            conversation.id, limit=1, offset=0
        )
        outbox_producer_service.produce_event(
            db,
            tenant_id=conversation.tenant_id,
            event_type=EventType.CONVERSATION_ABANDONED,
            payload=payload_builders.conversation_abandoned(
                conversation_id=conversation.id,
                receptionist_id=conversation.receptionist_id,
                mode=conversation.mode.value,
                channel=conversation.channel.value,
                message_count=message_count,
            ),
            dedup_key=f"conversation.abandoned:{conversation.id}",
        )
        result.abandoned += 1
        logger.info("conversation_abandoned_by_sweep", extra={"conversation_id": str(conversation.id)})
    return result

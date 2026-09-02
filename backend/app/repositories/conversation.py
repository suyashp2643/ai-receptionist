import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.conversation_summary import ConversationSummary
from app.repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository[Conversation]):  # type: ignore[type-var]
    model = Conversation

    def list_paginated(
        self, *, receptionist_id: uuid.UUID | None = None, limit: int, offset: int
    ) -> tuple[Sequence[Conversation], int]:
        conditions = [Conversation.tenant_id == self.tenant_id]
        if receptionist_id is not None:
            conditions.append(Conversation.receptionist_id == receptionist_id)

        total = self.db.scalar(select(func.count()).select_from(Conversation).where(*conditions)) or 0
        stmt = (
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all(), total

    def get_for_update(self, conversation_id: uuid.UUID) -> Conversation | None:
        """Locks the row for the duration of the caller's transaction —
        the documented mechanism serializing two simultaneous message
        submissions against the same conversation. Callers must commit (or
        rollback) promptly; this must never be held across a streaming
        provider call."""
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.tenant_id == self.tenant_id)
            .with_for_update()
        )
        return self.db.scalars(stmt).first()


class ConversationMessageRepository(TenantScopedRepository[ConversationMessage]):  # type: ignore[type-var]
    model = ConversationMessage

    def list_for_conversation(
        self, conversation_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[ConversationMessage], int]:
        conditions = [
            ConversationMessage.tenant_id == self.tenant_id,
            ConversationMessage.conversation_id == conversation_id,
        ]
        total = self.db.scalar(select(func.count()).select_from(ConversationMessage).where(*conditions)) or 0
        stmt = (
            select(ConversationMessage)
            .where(*conditions)
            .order_by(ConversationMessage.sequence_number)
            .limit(limit)
            .offset(offset)
        )
        return self.db.scalars(stmt).all(), total

    def get_by_idempotency_key(self, conversation_id: uuid.UUID, idempotency_key: str) -> ConversationMessage | None:
        stmt = select(ConversationMessage).where(
            ConversationMessage.tenant_id == self.tenant_id,
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.idempotency_key == idempotency_key,
        )
        return self.db.scalars(stmt).first()

    def next_sequence_number(self, conversation_id: uuid.UUID) -> int:
        """Call only while holding the conversation's row lock
        (see ConversationRepository.get_for_update) — otherwise two
        concurrent callers could compute the same next value."""
        current_max = self.db.scalar(
            select(func.max(ConversationMessage.sequence_number)).where(
                ConversationMessage.tenant_id == self.tenant_id,
                ConversationMessage.conversation_id == conversation_id,
            )
        )
        return (current_max if current_max is not None else -1) + 1


class ConversationSummaryRepository(TenantScopedRepository[ConversationSummary]):  # type: ignore[type-var]
    model = ConversationSummary

    def get_by_conversation_id(self, conversation_id: uuid.UUID) -> ConversationSummary | None:
        stmt = select(ConversationSummary).where(
            ConversationSummary.tenant_id == self.tenant_id,
            ConversationSummary.conversation_id == conversation_id,
        )
        return self.db.scalars(stmt).first()

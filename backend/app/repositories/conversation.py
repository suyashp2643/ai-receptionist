import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import aliased

from app.core.conversation_source import ConversationSource, source_case_expression
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.conversation_summary import ConversationSummary
from app.models.enums import ConversationStatus
from app.models.widget_visitor_session import WidgetVisitorSession
from app.repositories.base import TenantScopedRepository

# Allow-listed sort keys only — never interpolate a client-supplied column
# name into `order_by` (see app/api/v1/dashboard_conversations.py).
CONVERSATION_SORT_COLUMNS = {
    "started_at": Conversation.started_at,
    "last_message_at": Conversation.last_message_at,
}


@dataclass(frozen=True)
class ConversationFilters:
    receptionist_id: uuid.UUID | None = None
    sources: tuple[ConversationSource, ...] | None = None
    statuses: tuple[ConversationStatus, ...] | None = None
    started_after: datetime | None = None
    started_before: datetime | None = None
    only_safety_events: bool = False
    qualification_complete: bool | None = None
    search: str | None = None


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
            select(Conversation).where(*conditions).order_by(Conversation.started_at.desc()).limit(limit).offset(offset)
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

    def _base_dashboard_conditions(self, filters: ConversationFilters) -> list:
        conditions: list = [Conversation.tenant_id == self.tenant_id]
        if filters.receptionist_id is not None:
            conditions.append(Conversation.receptionist_id == filters.receptionist_id)
        if filters.statuses:
            conditions.append(Conversation.status.in_(filters.statuses))
        if filters.started_after is not None:
            conditions.append(Conversation.started_at >= filters.started_after)
        if filters.started_before is not None:
            conditions.append(Conversation.started_at < filters.started_before)
        if filters.only_safety_events:
            conditions.append(Conversation.had_safety_event.is_(True))
        if filters.qualification_complete is not None:
            conditions.append(Conversation.qualification_complete.is_(filters.qualification_complete))
        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            contact_match = exists(
                select(Contact.id).where(
                    Contact.tenant_id == self.tenant_id,
                    Contact.conversation_id == Conversation.id,
                    or_(
                        Contact.name.ilike(pattern),
                        Contact.normalized_email.ilike(pattern),
                        Contact.normalized_phone.ilike(pattern),
                    ),
                )
            )
            conditions.append(or_(Conversation.visitor_reference.ilike(pattern), contact_match))
        return conditions

    def list_dashboard(
        self,
        *,
        filters: ConversationFilters,
        sort_column: str,
        sort_descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[tuple[Conversation, ConversationSource]], int]:
        """Bounded, filterable, sortable list for the operations dashboard.
        Returns (rows, total) where each row pairs a Conversation with its
        already-computed ConversationSource (see
        app/core/conversation_source.py) — never re-derived per-row in
        Python from a second query, and never requires loading any
        message."""
        session_alias = aliased(WidgetVisitorSession)
        source_expr = source_case_expression(Conversation.mode, session_alias.is_platform_preview)

        conditions = self._base_dashboard_conditions(filters)
        if filters.sources:
            source_conditions = [source_expr == s.value for s in filters.sources]
            conditions.append(or_(*source_conditions))

        base_from = Conversation.__table__.outerjoin(session_alias, session_alias.conversation_id == Conversation.id)

        total = self.db.scalar(select(func.count(Conversation.id)).select_from(base_from).where(*conditions)) or 0

        sort_col = CONVERSATION_SORT_COLUMNS[sort_column]
        order = sort_col.desc() if sort_descending else sort_col.asc()

        stmt = (
            select(Conversation, source_expr)
            .select_from(base_from)
            .where(*conditions)
            .order_by(order, Conversation.id)
            .limit(limit)
            .offset(offset)
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], ConversationSource(row[1])) for row in rows], total


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

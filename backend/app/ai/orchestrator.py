"""The conversation orchestrator — the auditable state machine tying every
Phase 4 service together. Each numbered step below corresponds to a
separate, independently-testable module; this class only sequences them.

Concurrency: `submit_message` deliberately does NOT follow this codebase's
usual "exactly one commit per request, via app.db.session.get_db" pattern
— for a `StreamingResponse`-returning route, FastAPI's dependency-cleanup
(the thing that calls that one `db.commit()`) fires as soon as the
endpoint function *returns the response object*, not after the streamed
body finishes sending. Since `event_stream()`'s generator body — where
all the real work happens — is lazy and only runs *after* the endpoint
has already returned, relying on that single automatic commit would
either commit nothing real (if it fires before the generator's writes
exist) or, if the session auto-begins a fresh implicit transaction for
the generator's later writes (which it does), leave that transaction
permanently uncommitted — holding any row lock forever and deadlocking
the next request against the same conversation. This was caught live: a
second message to the same conversation hung indefinitely with
`get_for_update`'s `SELECT ... FOR UPDATE` blocked on a lock the first
request's connection was still idling on.

The fix is for `submit_message` to manage its own short transactions
explicitly via `db.commit()` at each phase boundary — exactly the design
the docstring below describes: the row lock from `get_for_update` is held
only for the two short phases that read/write conversation state, never
across the provider streaming phase in between. This requires
`tests/conftest.py`'s `db_backed_client` fixture to let application code
call `.commit()` normally — its session already uses
`join_transaction_mode="create_savepoint"` for exactly this purpose; an
earlier, redundant extra `begin_nested()` wrapper in that fixture (fixed
alongside this) is what made an initial attempt at this design appear to
conflict with the test session's transaction handling.

Two simultaneous submissions to the same conversation serialize at the
row lock (never interleaved, never corrupt state) rather than blocking
for an entire turn's duration. A client that disconnects mid-stream is
detected via `is_disconnected` (not wired to a real check in the current
sync route — see `app/api/v1/conversations.py`), and whatever was
generated so far is still persisted as the assistant's message so the
transcript never desyncs from what the client saw.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.errors import (
    ConversationNotActiveError,
    ConversationNotFoundError,
    ReceptionistWorkflowMissingError,
)
from app.ai.providers.base import (
    AIProvider,
    ConversationContext,
    GenerateRequest,
    ProviderError,
    ProviderFinishReason,
    ProviderMessage,
    QualificationState,
    RetrievedSource,
    SafetyDirective,
    ToolExecutionResult,
)
from app.ai.qualification import ExtractionOutcome, process_message, to_field_summary
from app.ai.retrieval import RetrievalQuery, retrieve
from app.ai.safety import evaluate_safety
from app.ai.system_instructions import build_system_instruction
from app.ai.tools.base import ToolContext, execute_tool
from app.ai.tools.registry import PHASE_4_TOOL_NAMES, TOOL_REGISTRY
from app.core.allowlists import MANDATORY_SAFETY_RULES
from app.integrations import payload_builders
from app.integrations.envelope import EventType
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.conversation_summary import ConversationSummary
from app.models.enums import ConversationChannel, ConversationMessageRole, ConversationMode, ConversationStatus
from app.models.receptionist import Receptionist
from app.models.receptionist_workflow import ReceptionistWorkflow
from app.repositories.business_profile import BusinessProfileRepository
from app.repositories.conversation import (
    ConversationMessageRepository,
    ConversationRepository,
    ConversationSummaryRepository,
)
from app.repositories.industry_template import IndustryTemplateRepository
from app.repositories.receptionist import ReceptionistRepository, ReceptionistWorkflowRepository
from app.schemas.qualification import QualificationSchema
from app.services import outbox_producer_service

logger = logging.getLogger("app.ai.orchestrator")

_PREFERRED_ACTION_ORDER = [
    "request_appointment",
    "request_viewing",
    "request_reservation",
    "request_demo",
    "request_test_drive",
    "request_service_visit",
    "request_callback",
    "request_human_handoff",
    "capture_contact",
]

MAX_TOOL_ITERATIONS = 2


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _compute_missing_field_keys(schema: QualificationSchema, collected_data: dict) -> list[str]:
    ordered = sorted(schema.fields, key=lambda f: f.display_order)
    return [f.key for f in ordered if f.required and f.key not in collected_data]


def _provider_error_event(exc: ProviderError) -> dict:
    return {
        "event": "response.error",
        "data": {"code": exc.code, "message": "The assistant is temporarily unavailable."},
    }


def _pick_recommended_action(enabled_actions: list[str], *, qualification_complete: bool) -> str | None:
    if not qualification_complete:
        return None
    for action in _PREFERRED_ACTION_ORDER:
        if action in enabled_actions:
            return action
    return None


def _collect_citations(retrieved_sources: list[RetrievedSource], tool_results: list[ToolExecutionResult]) -> list[dict]:
    citations = [
        {"source_id": s.source_id, "source_type": s.source_type, "title": s.title, "score": s.score}
        for s in retrieved_sources
    ]
    for result in tool_results:
        if result.tool_name == "search_business_knowledge" and result.status == "ok":
            for item in result.output.get("results", []):
                citations.append(
                    {
                        "source_id": item.get("source_id"),
                        "source_type": item.get("source_type"),
                        "title": item.get("title"),
                        "score": item.get("score"),
                    }
                )
    seen: set[Any] = set()
    deduped = []
    for citation in citations:
        key = citation["source_id"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped


class ConversationOrchestrator:
    def __init__(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        provider: AIProvider,
        retrieval_limit: int = 5,
        max_context_chars: int = 12000,
        is_disconnected: Callable[[], bool] | None = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.provider = provider
        self.retrieval_limit = retrieval_limit
        self.max_context_chars = max_context_chars
        self._is_disconnected = is_disconnected or (lambda: False)

        self.conversation_repo = ConversationRepository(db, tenant_id)
        self.message_repo = ConversationMessageRepository(db, tenant_id)
        self.summary_repo = ConversationSummaryRepository(db, tenant_id)
        self.receptionist_repo = ReceptionistRepository(db, tenant_id)
        self.workflow_repo = ReceptionistWorkflowRepository(db, tenant_id)

    # ------------------------------------------------------------------
    # Step 1: validate tenant, receptionist and workflow / start conversation
    # ------------------------------------------------------------------
    def start_conversation(
        self,
        *,
        receptionist_id: uuid.UUID,
        visitor_reference: str | None = None,
        locale: str = "en",
        mode: ConversationMode = ConversationMode.TEST,
        channel: ConversationChannel = ConversationChannel.DASHBOARD_TEST,
    ) -> Conversation:
        receptionist = self.receptionist_repo.get(receptionist_id)
        if receptionist is None:
            raise ConversationNotFoundError("Receptionist not found.")
        workflow = self.workflow_repo.get_by_receptionist_id(receptionist_id)
        if workflow is None:
            # Should not happen given Phase 3's invariant (a workflow is
            # always created alongside its receptionist), but a test
            # conversation must never be started against a schema-less
            # workflow silently.
            raise ReceptionistWorkflowMissingError("This receptionist has no workflow configured.")

        schema = QualificationSchema.model_validate(workflow.qualification_schema)
        missing = _compute_missing_field_keys(schema, {})

        conversation = Conversation(
            tenant_id=self.tenant_id,
            receptionist_id=receptionist_id,
            mode=mode,
            channel=channel,
            provider=self.provider.name,
            status=ConversationStatus.ACTIVE,
            visitor_reference=visitor_reference,
            locale=locale,
            collected_data={},
            missing_required_fields=missing,
            qualification_complete=len(missing) == 0,
            safety_state={},
        )
        self.conversation_repo.add(conversation)
        self.db.flush()
        self.db.refresh(conversation)
        logger.info(
            "conversation_started",
            extra={
                "conversation_id": str(conversation.id),
                "receptionist_id": str(receptionist_id),
                "provider": self.provider.name,
            },
        )
        return conversation

    # ------------------------------------------------------------------
    # Message submission — the full 16-step state machine, yielding SSE
    # event dicts ({"event": str, "data": dict}) as it goes.
    # ------------------------------------------------------------------
    def submit_message(
        self, conversation_id: uuid.UUID, *, content: str, idempotency_key: str | None = None
    ) -> Iterator[dict]:
        """Thin wrapper providing a blanket safety net: whichever line
        inside `_submit_message_impl` raises — an early validation error,
        a provider failure not already handled by `_persist_failure`, or
        a genuine bug — this guarantees the row lock's transaction is
        rolled back rather than left "idle in transaction" forever. Normal
        (non-exception) exits are handled by the explicit commits inside
        the implementation itself."""
        try:
            yield from self._submit_message_impl(conversation_id, content=content, idempotency_key=idempotency_key)
        except Exception:
            self.db.rollback()
            raise

    def _submit_message_impl(
        self, conversation_id: uuid.UUID, *, content: str, idempotency_key: str | None = None
    ) -> Iterator[dict]:
        turn_start = time.monotonic()

        conversation = self.conversation_repo.get_for_update(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("Conversation not found.")
        if conversation.status != ConversationStatus.ACTIVE:
            raise ConversationNotActiveError("This conversation is no longer active.")

        receptionist = self.receptionist_repo.get(conversation.receptionist_id)
        workflow = self.workflow_repo.get_by_receptionist_id(conversation.receptionist_id)
        if receptionist is None or workflow is None:
            raise ReceptionistWorkflowMissingError("This receptionist's workflow is missing.")

        existing_user_message = None
        if idempotency_key:
            existing_user_message = self.message_repo.get_by_idempotency_key(conversation_id, idempotency_key)

        if existing_user_message is not None:
            following = self._get_message_at_sequence(conversation_id, existing_user_message.sequence_number + 1)
            if following is not None and following.role == ConversationMessageRole.ASSISTANT:
                # Nothing was written, but `get_for_update` above still
                # acquired the row lock in an implicit transaction — commit
                # (a no-op for data, since nothing changed) to release it
                # rather than leaving it held until some later, unrelated
                # use of this session closes it. The commit runs *after*
                # `_replay` so its attribute reads happen on non-expired
                # objects — reading them post-commit would silently open a
                # second, never-closed implicit transaction of its own.
                try:
                    yield from self._replay(conversation, existing_user_message, following)
                finally:
                    self.db.commit()
                return
            # A previous attempt stored the user message but failed before
            # an assistant reply was persisted — reprocess without
            # inserting a second user message.
            user_message = existing_user_message
            sequence_number = existing_user_message.sequence_number
            content = existing_user_message.content
        else:
            sequence_number = self.message_repo.next_sequence_number(conversation_id)
            user_message = ConversationMessage(
                tenant_id=self.tenant_id,
                conversation_id=conversation_id,
                role=ConversationMessageRole.USER,
                content=content,
                sequence_number=sequence_number,
                idempotency_key=idempotency_key,
                citations=[],
                safety_labels=[],
            )
            self.message_repo.add(user_message)
            conversation.last_message_at = _utcnow()

        self.db.commit()

        yield {
            "event": "message.started",
            "data": {
                "conversation_id": str(conversation_id),
                "user_message_id": str(user_message.id),
                "sequence_number": sequence_number,
            },
        }

        # Step 2: deterministic safety pre-check — outside the provider,
        # and always evaluated before anything else proceeds.
        industry_template_key = self._industry_template_key(receptionist.industry_template_id)
        safety_directive = evaluate_safety(content, industry_template_key=industry_template_key)

        # Step 4: retrieval (skipped entirely if a safety response will be
        # used instead — no reason to spend the query).
        retrieved_sources: list[RetrievedSource] = []
        if not safety_directive.triggered:
            retrieved_sources = retrieve(
                self.db, tenant_id=self.tenant_id, query=RetrievalQuery(text=content, limit=self.retrieval_limit)
            )
        yield {
            "event": "retrieval.completed",
            "data": {
                "count": len(retrieved_sources),
                "sources": [
                    {"source_id": s.source_id, "source_type": s.source_type, "title": s.title, "score": s.score}
                    for s in retrieved_sources
                ],
            },
        }

        # Steps 6-8: qualification extraction, validation, and collected-data update.
        schema = QualificationSchema.model_validate(workflow.qualification_schema)
        all_field_summaries = [to_field_summary(f) for f in schema.fields]
        collected_data = dict(conversation.collected_data)
        missing_before = _compute_missing_field_keys(schema, collected_data)
        pending_field = None
        if missing_before:
            pending_field = next((f for f in all_field_summaries if f.key == missing_before[0]), None)

        extraction_outcome = ExtractionOutcome()
        if not safety_directive.triggered:
            extraction_outcome = process_message(
                all_fields=all_field_summaries,
                pending_field=pending_field,
                collected_data=collected_data,
                raw_message=content,
            )
            collected_data.update(extraction_outcome.captured)
            collected_data.update(extraction_outcome.corrected)

        missing_after = _compute_missing_field_keys(schema, collected_data)
        qualification_complete = len(missing_after) == 0
        new_pending = None
        if missing_after:
            new_pending = next((f for f in all_field_summaries if f.key == missing_after[0]), None)
        missing_summaries = [f for f in all_field_summaries if f.key in missing_after]
        just_captured = [f for f in all_field_summaries if f.key in extraction_outcome.captured]
        just_corrected = [f for f in all_field_summaries if f.key in extraction_outcome.corrected]

        # Short transaction #2: persist the qualification audit event (if
        # anything happened) and the updated conversation state. The row
        # lock from phase 1 was already released by the commit above, so
        # it's re-acquired here — never held across the streaming phase
        # that follows this block.
        conversation = self.conversation_repo.get_for_update(conversation_id)
        assert conversation is not None  # already validated to exist in phase 1
        if extraction_outcome.captured or extraction_outcome.corrected or extraction_outcome.rejected:
            audit_seq = self.message_repo.next_sequence_number(conversation_id)
            audit_message = ConversationMessage(
                tenant_id=self.tenant_id,
                conversation_id=conversation_id,
                role=ConversationMessageRole.TOOL,
                content="",
                sequence_number=audit_seq,
                tool_name="qualification_extraction",
                tool_input={"pending_field": pending_field.key if pending_field else None},
                tool_output={
                    "captured": extraction_outcome.captured,
                    "corrected": extraction_outcome.corrected,
                    "rejected": [r.model_dump() for r in extraction_outcome.rejected],
                },
                citations=[],
                safety_labels=[],
            )
            self.message_repo.add(audit_message)
        conversation.collected_data = collected_data
        conversation.missing_required_fields = missing_after
        conversation.qualification_complete = qualification_complete
        if safety_directive.triggered:
            safety_state = dict(conversation.safety_state)
            triggered_categories = list(safety_state.get("triggered_categories", []))
            triggered_categories.append(safety_directive.category)
            safety_state["triggered_categories"] = triggered_categories[-20:]
            conversation.safety_state = safety_state
            # Phase 8: notify subscribed connections a safety-relevant
            # response was used. Pure DB work (no network call) — safe to
            # do while this phase's row lock is held, same as the audit
            # message write just above; the actual outbound delivery
            # attempt happens later, entirely outside this transaction, in
            # app/services/outbox_worker_service.py. Never includes the
            # triggering message text — see payload_builders and
            # envelope.py's PII policy.
            outbox_producer_service.produce_event(
                self.db,
                tenant_id=self.tenant_id,
                event_type=EventType.SAFETY_ESCALATION_DETECTED,
                payload=payload_builders.safety_escalation_detected(
                    conversation_id=conversation_id,
                    receptionist_id=receptionist.id,
                    category=safety_directive.category,
                    channel=conversation.channel.value,
                ),
                dedup_key=f"safety.escalation_detected:{conversation_id}:{sequence_number}",
                correlation_id=conversation_id,
            )
        self.db.commit()

        # Step 5 + 11: tool gating — only when the workflow allows
        # answering questions at all, and never when a safety response
        # will be used instead.
        allowed_tool_names: set[str] = set()
        if "answer_questions" in (workflow.enabled_actions or []):
            allowed_tool_names = set(PHASE_4_TOOL_NAMES)
        tool_definitions = []
        if not safety_directive.triggered:
            tool_definitions = TOOL_REGISTRY.definitions(allowed_names=allowed_tool_names)

        business_name = self._business_name(receptionist)
        recommended_action = _pick_recommended_action(
            list(workflow.enabled_actions or []), qualification_complete=qualification_complete
        )

        context = ConversationContext(
            receptionist_name=receptionist.name,
            business_name=business_name,
            tone=receptionist.tone,
            retrieved_sources=retrieved_sources,
            qualification=QualificationState(
                next_field=new_pending,
                collected_data=collected_data,
                missing_required_fields=missing_after,
                missing_field_summaries=missing_summaries,
                qualification_complete=qualification_complete,
                just_captured=just_captured,
                just_corrected=just_corrected,
                just_rejected=extraction_outcome.rejected,
            ),
            safety=safety_directive,
            tool_results=[],
            recommended_next_action=recommended_action,
            turn_index=sequence_number,
        )

        provider_messages = self._build_provider_messages(
            conversation_id, receptionist=receptionist, workflow=workflow, retrieved_sources=retrieved_sources
        )

        tool_context = ToolContext(tenant_id=self.tenant_id, receptionist_id=receptionist.id)
        tool_events: list[tuple[str, str, dict, ToolExecutionResult]] = []

        # Steps 10-12: tool-call decision pass, validated + executed
        # against the server allow-list. Bounded to avoid any possibility
        # of an infinite loop even though the mock provider never requests
        # more than one tool call per turn.
        if tool_definitions and not safety_directive.triggered:
            for _ in range(MAX_TOOL_ITERATIONS):
                decision_request = GenerateRequest(messages=provider_messages, tools=tool_definitions, context=context)
                try:
                    decision = self.provider.generate(decision_request)
                except ProviderError as exc:
                    yield _provider_error_event(exc)
                    self._persist_failure(conversation, error_code=exc.code)
                    return
                if decision.finish_reason != ProviderFinishReason.TOOL_CALLS or not decision.tool_calls:
                    break
                call = decision.tool_calls[0]
                yield {"event": "tool.started", "data": {"tool_name": call.name, "call_id": call.id}}
                result = execute_tool(
                    TOOL_REGISTRY,
                    call_id=call.id,
                    name=call.name,
                    arguments=call.arguments,
                    allowed_names=allowed_tool_names,
                    db=self.db,
                    context=tool_context,
                )
                yield {
                    "event": "tool.completed",
                    "data": {"tool_name": call.name, "call_id": call.id, "status": result.status},
                }
                tool_events.append((call.id, call.name, call.arguments, result))
                context = context.model_copy(update={"tool_results": context.tool_results + [result]})

        # Step 13: generate and stream the final response — no transaction
        # or row lock held for the duration of this loop.
        accumulated = ""
        provider_message_id: str | None = None
        is_fallback_response = False
        stream_request = GenerateRequest(messages=provider_messages, tools=tool_definitions, context=context)
        try:
            for chunk in self.provider.stream(stream_request):
                if self._is_disconnected():
                    logger.info("client_disconnected_mid_stream", extra={"conversation_id": str(conversation_id)})
                    break
                if chunk.delta:
                    accumulated += chunk.delta
                    yield {"event": "response.delta", "data": {"delta": chunk.delta}}
                if chunk.provider_message_id:
                    provider_message_id = chunk.provider_message_id
                if chunk.is_fallback:
                    is_fallback_response = True
        except ProviderError as exc:
            yield _provider_error_event(exc)
            self._persist_failure(conversation, error_code=exc.code)
            return

        latency_ms = int((time.monotonic() - turn_start) * 1000)

        # Short transaction #3: persist tool events, the assistant
        # message, and the final conversation state. Re-acquires the row
        # lock one last time — released again by the commit at the end of
        # this block, so nothing is held once the response finishes.
        conversation = self.conversation_repo.get_for_update(conversation_id)
        assert conversation is not None
        # `next_sequence_number` queries MAX(sequence_number) against the
        # database — with this session's `autoflush=False`, calling it more
        # than once in this block would repeatedly see the *same* max (none
        # of these ConversationMessage rows are flushed until the commit
        # below), silently handing out duplicate sequence numbers that only
        # fail at flush time via the unique (conversation_id,
        # sequence_number) constraint. Query it once and increment locally.
        next_seq = self.message_repo.next_sequence_number(conversation_id)
        for call_id, call_name, call_arguments, result in tool_events:
            tool_seq = next_seq
            next_seq += 1
            self.message_repo.add(
                ConversationMessage(
                    tenant_id=self.tenant_id,
                    conversation_id=conversation_id,
                    role=ConversationMessageRole.TOOL,
                    content="",
                    sequence_number=tool_seq,
                    tool_name=call_name,
                    tool_call_id=call_id,
                    tool_input=call_arguments,
                    tool_output=result.output,
                    citations=[],
                    safety_labels=[],
                )
            )

        citations = _collect_citations(retrieved_sources, [r for *_, r in tool_events])
        safety_labels = [safety_directive.category] if safety_directive.triggered else []
        assistant_seq = next_seq
        assistant_message = ConversationMessage(
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            role=ConversationMessageRole.ASSISTANT,
            content=accumulated,
            sequence_number=assistant_seq,
            provider_message_id=provider_message_id,
            citations=citations,
            safety_labels=safety_labels,
            is_fallback_response=is_fallback_response,
            latency_ms=latency_ms,
        )
        self.message_repo.add(assistant_message)
        conversation.last_message_at = _utcnow()
        conversation.last_error_code = None
        if safety_directive.triggered:
            conversation.had_safety_event = True
            if safety_directive.category == "clinic_urgent":
                conversation.had_clinic_emergency = True
        # `assistant_message.id` is a client-side `default=uuid.uuid4`
        # column — SQLAlchemy only evaluates that default (and assigns it
        # onto the instance) when the row is actually flushed, so reading
        # `.id` before any flush would silently return None. `flush()`
        # (unlike `commit()`) does not expire already-loaded attributes, so
        # `conversation.status.value` is also safe to read right after it —
        # reading either only after the *commit* below would instead
        # silently reopen a fresh implicit transaction that nothing would
        # ever close on this generator's connection.
        self.db.flush()
        assistant_message_id = str(assistant_message.id)
        conversation_status_value = conversation.status.value
        self.db.commit()

        logger.info(
            "response_completed",
            extra={
                "conversation_id": str(conversation_id),
                "latency_ms": latency_ms,
                "safety_category": safety_directive.category,
                "tool_count": len(tool_events),
                "retrieval_count": len(retrieved_sources),
            },
        )

        yield {
            "event": "response.completed",
            "data": {
                "message_id": assistant_message_id,
                "sequence_number": assistant_seq,
                "content": accumulated,
                "citations": citations,
                "safety_labels": safety_labels,
            },
        }
        yield {
            "event": "conversation.updated",
            "data": {
                "collected_data": collected_data,
                "missing_required_fields": missing_after,
                "qualification_complete": qualification_complete,
                "status": conversation_status_value,
            },
        }

    def _replay(
        self,
        conversation: Conversation,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
    ) -> Iterator[dict]:
        """An idempotent duplicate submission — the turn already completed
        successfully, so re-emit its stored result rather than reprocessing
        (which would otherwise re-run retrieval/qualification/tools and
        risk a different outcome the second time)."""
        yield {
            "event": "message.started",
            "data": {
                "conversation_id": str(conversation.id),
                "user_message_id": str(user_message.id),
                "sequence_number": user_message.sequence_number,
                "replay": True,
            },
        }
        yield {
            "event": "response.completed",
            "data": {
                "message_id": str(assistant_message.id),
                "sequence_number": assistant_message.sequence_number,
                "content": assistant_message.content,
                "citations": assistant_message.citations,
                "safety_labels": assistant_message.safety_labels,
                "replay": True,
            },
        }
        yield {
            "event": "conversation.updated",
            "data": {
                "collected_data": conversation.collected_data,
                "missing_required_fields": conversation.missing_required_fields,
                "qualification_complete": conversation.qualification_complete,
                "status": conversation.status.value,
            },
        }

    def _persist_failure(self, conversation: Conversation, *, error_code: str) -> None:
        conversation.last_error_code = error_code
        self.db.commit()
        logger.warning(
            "conversation_turn_failed",
            extra={"conversation_id": str(conversation.id), "error_code": error_code},
        )

    def _get_message_at_sequence(self, conversation_id: uuid.UUID, sequence_number: int) -> ConversationMessage | None:
        stmt = select(ConversationMessage).where(
            ConversationMessage.tenant_id == self.tenant_id,
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.sequence_number == sequence_number,
        )
        return self.db.scalars(stmt).first()

    def _industry_template_key(self, industry_template_id: uuid.UUID | None) -> str | None:
        if industry_template_id is None:
            return None
        template = IndustryTemplateRepository(self.db).get_by_id(industry_template_id)
        return template.key if template is not None else None

    def _business_name(self, receptionist: Receptionist) -> str:
        profile = BusinessProfileRepository(self.db).get_by_tenant_id(self.tenant_id)
        if profile is not None and profile.business_name:
            return profile.business_name
        return receptionist.name

    def _build_provider_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        receptionist: Receptionist,
        workflow: ReceptionistWorkflow,
        retrieved_sources: list[RetrievedSource],
    ) -> list[ProviderMessage]:
        """Assembled for contract completeness (what a real provider would
        receive) — the mock provider primarily uses `context`, reading only
        the latest user message out of this list."""
        template_key = self._industry_template_key(receptionist.industry_template_id) or ""
        mandatory = list(MANDATORY_SAFETY_RULES.get(template_key, ()))
        system_text = build_system_instruction(
            receptionist_name=receptionist.name,
            business_name=self._business_name(receptionist),
            tone=receptionist.tone,
            mandatory_safety_rules=mandatory,
            extra_safety_rules=list(workflow.safety_rules or []),
            tool_names=sorted(PHASE_4_TOOL_NAMES) if "answer_questions" in (workflow.enabled_actions or []) else [],
            retrieved_sources=retrieved_sources,
            max_chars=self.max_context_chars,
        )
        messages: list[ProviderMessage] = [ProviderMessage(role="system", content=system_text)]

        history, _ = self.message_repo.list_for_conversation(conversation_id, limit=200, offset=0)
        for message in history:
            if message.role in (ConversationMessageRole.USER, ConversationMessageRole.ASSISTANT):
                messages.append(ProviderMessage(role=message.role.value, content=message.content))
        return messages

    # ------------------------------------------------------------------
    # Conversation completion — step 16: create the summary.
    # ------------------------------------------------------------------
    def complete_conversation(self, conversation_id: uuid.UUID) -> tuple[Conversation, ConversationSummary]:
        conversation = self.conversation_repo.get_for_update(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("Conversation not found.")
        if conversation.status != ConversationStatus.ACTIVE:
            raise ConversationNotActiveError("This conversation is already completed or abandoned.")

        receptionist = self.receptionist_repo.get(conversation.receptionist_id)
        workflow = self.workflow_repo.get_by_receptionist_id(conversation.receptionist_id)
        if receptionist is None or workflow is None:
            raise ReceptionistWorkflowMissingError("This receptionist's workflow is missing.")

        schema = QualificationSchema.model_validate(workflow.qualification_schema)
        all_field_summaries = [to_field_summary(f) for f in schema.fields]
        missing_summaries = [f for f in all_field_summaries if f.key in conversation.missing_required_fields]
        recommended_action = _pick_recommended_action(
            list(workflow.enabled_actions or []), qualification_complete=conversation.qualification_complete
        )

        context = ConversationContext(
            receptionist_name=receptionist.name,
            business_name=self._business_name(receptionist),
            tone=receptionist.tone,
            qualification=QualificationState(
                collected_data=conversation.collected_data,
                missing_required_fields=conversation.missing_required_fields,
                missing_field_summaries=missing_summaries,
                qualification_complete=conversation.qualification_complete,
            ),
            safety=SafetyDirective(),
            recommended_next_action=recommended_action,
        )

        result = self.provider.summarize(context)

        summary = ConversationSummary(
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            summary=result.summary,
            captured_requirements=result.captured_requirements,
            unresolved_questions=result.unresolved_questions,
            recommended_next_action=result.recommended_next_action,
            generated_by_provider=self.provider.name,
        )
        self.summary_repo.add(summary)
        conversation.status = ConversationStatus.COMPLETED
        conversation.completed_at = _utcnow()

        _, message_count = self.message_repo.list_for_conversation(conversation_id, limit=1, offset=0)
        outbox_producer_service.produce_event(
            self.db,
            tenant_id=self.tenant_id,
            event_type=EventType.CONVERSATION_COMPLETED,
            payload=payload_builders.conversation_completed(
                conversation_id=conversation_id,
                receptionist_id=conversation.receptionist_id,
                mode=conversation.mode.value,
                channel=conversation.channel.value,
                message_count=message_count,
            ),
            dedup_key=f"conversation.completed:{conversation_id}",
        )

        self.db.flush()
        self.db.refresh(conversation)
        self.db.refresh(summary)

        logger.info("conversation_completed", extra={"conversation_id": str(conversation_id)})
        return conversation, summary

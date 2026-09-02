"""Private, authenticated test-conversation endpoints.

Minimum role is `member` (not `admin`) throughout — running a private test
conversation does not modify receptionist configuration, so the same
read-permission tier that can already view a receptionist's settings can
start and drive a test conversation too. Only receptionist/workflow
*configuration* routes (elsewhere) remain admin-gated. No CSRF header is
required on these routes: every one is Bearer-token authenticated, not
cookie-authenticated, matching every other tenant-scoped route in this
API (CSRF only applies to /auth/refresh and /auth/logout, the only
cookie-authenticated state-changing routes).

There is deliberately no separate `GET .../stream` route and no
`.../retry` route — see docs/api.md's "Test conversations" section for
why: the SSE stream is the direct response of `POST .../messages`, and
retry is just resubmitting that same call with the same idempotency key.
"""

import json
import uuid
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import AbstractContextManager

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai.errors import ConversationError
from app.ai.orchestrator import ConversationOrchestrator
from app.ai.providers.base import ProviderConfigurationError
from app.ai.providers.factory import get_provider
from app.api.deps import TenantContext, get_db, get_session_scope_factory, get_tenant_context
from app.config import Settings, get_settings
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus
from app.repositories.conversation import (
    ConversationMessageRepository,
    ConversationRepository,
    ConversationSummaryRepository,
)
from app.repositories.receptionist import ReceptionistRepository
from app.schemas.conversation import (
    CompleteConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageRead,
    ConversationRead,
    ConversationSummaryRead,
    SendMessageRequest,
    StartConversationRequest,
)

router = APIRouter()

MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 20


def _get_conversation_or_404(conversation_id: uuid.UUID, ctx: TenantContext, db: Session) -> Conversation:
    conversation = ConversationRepository(db, ctx.tenant_id).get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


def _resolve_provider_or_500(settings: Settings):  # noqa: ANN201
    try:
        return get_provider(settings)
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI provider is not configured correctly."
        ) from exc


def _format_sse(event: dict) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"


def _bounded(value: int, *, minimum: int = 0, maximum: int = MAX_PAGE_SIZE) -> int:
    return max(minimum, min(value, maximum))


class _StopSyncGenerator(Exception):
    """Not `StopIteration`, deliberately: PEP 479 converts a `StopIteration`
    that propagates out of a coroutine into `RuntimeError: coroutine raised
    StopIteration`, so it can never be caught as `StopIteration` by code
    `await`ing a threadpool-dispatched `next()` call. Converting it inside
    the thread itself, before it crosses that boundary, is required —
    exactly what `starlette.concurrency.iterate_in_threadpool`'s own
    `_next`/`_StopIteration` pair does for the same reason."""


def _next_or_raise_stop_marker(iterator: Generator[str, None, None]) -> str:
    try:
        return next(iterator)
    except StopIteration:
        raise _StopSyncGenerator from None


async def stream_sync_generator(sync_gen: Generator[str, None, None]) -> AsyncGenerator[str, None]:
    """Adapts a sync generator into the async one `StreamingResponse` needs
    for its cleanup to be deterministic — extracted as its own top-level,
    directly-testable function (see `tests/test_db_session_lifecycle.py`'s
    `TestStreamSyncGeneratorCancellation`) rather than an inline closure,
    specifically so its cancellation-safety can be unit-tested without a
    real HTTP client or a real network disconnect (nothing in this
    codebase's test transport can reliably simulate one for a provider as
    fast as the mock — this exact gap in coverage is how the bug this
    function fixes went unnoticed until a live pass against a real TCP
    client).

    `StreamingResponse(sync_gen, ...)` — passing a *sync* generator
    directly — looks like it should work and does, for the happy path.
    But Starlette wraps a sync iterable in `iterate_in_threadpool`, which
    dispatches each `next()` call to a worker thread and — confirmed by
    reading its source, and confirmed live — never calls `.close()` on the
    generator under any circumstance, including a real client disconnect
    (which only cancels the *task awaiting* the next `next()` result; it
    cannot and does not interrupt the worker thread already dispatched, and
    nothing afterward ever resumes or closes the generator). Any
    `with`/`try–finally` cleanup inside that generator — here, a
    `session_scope`-owned database session — then never runs, for as long
    as the process is alive.

    Making this wrapper genuinely `async` sidesteps `iterate_in_threadpool`
    entirely (`StreamingResponse` uses an `AsyncIterable` body directly).
    A cancelled task now delivers `CancelledError` straight into *this*
    generator's own suspension point, and the `finally` below — which runs
    for `GeneratorExit`/`CancelledError` exactly like any other exception —
    deterministically closes `sync_gen`, running whatever cleanup it owns,
    before this coroutine is allowed to finish unwinding.
    """
    try:
        while True:
            try:
                # Not `await run_in_threadpool(next, sync_gen)` directly:
                # PEP 479 turns a bare `StopIteration` raised inside a
                # coroutine into `RuntimeError: coroutine raised
                # StopIteration` before it would ever reach an `except
                # StopIteration` here — confirmed live, not just from the
                # changelog — so the thread-side helper converts it to a
                # distinct exception first, exactly like Starlette's own
                # `_next`/`_StopIteration` inside `iterate_in_threadpool`.
                chunk = await run_in_threadpool(_next_or_raise_stop_marker, sync_gen)
            except _StopSyncGenerator:
                return
            yield chunk
    finally:
        await run_in_threadpool(sync_gen.close)


@router.post(
    "/tenants/{tenant_id}/receptionists/{receptionist_id}/test-conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def start_test_conversation(
    receptionist_id: uuid.UUID,
    payload: StartConversationRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ConversationRead:
    if ReceptionistRepository(db, ctx.tenant_id).get(receptionist_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receptionist not found")

    provider = _resolve_provider_or_500(settings)
    orchestrator = ConversationOrchestrator(
        db,
        tenant_id=ctx.tenant_id,
        provider=provider,
        retrieval_limit=settings.retrieval_result_limit,
        max_context_chars=settings.max_conversation_context_chars,
    )
    try:
        conversation = orchestrator.start_conversation(
            receptionist_id=receptionist_id, visitor_reference=payload.visitor_reference, locale=payload.locale
        )
    except ConversationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ConversationRead.model_validate(conversation)


@router.get("/tenants/{tenant_id}/test-conversations", response_model=ConversationListResponse)
def list_test_conversations(
    receptionist_id: uuid.UUID | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    bounded_limit = _bounded(limit, minimum=1)
    bounded_offset = _bounded(offset)
    items, total = ConversationRepository(db, ctx.tenant_id).list_paginated(
        receptionist_id=receptionist_id, limit=bounded_limit, offset=bounded_offset
    )
    return ConversationListResponse(
        items=[ConversationRead.model_validate(c) for c in items],
        total=total,
        limit=bounded_limit,
        offset=bounded_offset,
    )


@router.get("/tenants/{tenant_id}/test-conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_test_conversation(
    conversation_id: uuid.UUID,
    message_limit: int = DEFAULT_PAGE_SIZE,
    message_offset: int = 0,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    conversation = _get_conversation_or_404(conversation_id, ctx, db)
    bounded_limit = _bounded(message_limit, minimum=1)
    bounded_offset = _bounded(message_offset)
    messages, total = ConversationMessageRepository(db, ctx.tenant_id).list_for_conversation(
        conversation_id, limit=bounded_limit, offset=bounded_offset
    )
    summary = ConversationSummaryRepository(db, ctx.tenant_id).get_by_conversation_id(conversation_id)
    return ConversationDetailResponse(
        conversation=ConversationRead.model_validate(conversation),
        messages=[ConversationMessageRead.model_validate(m) for m in messages],
        message_total=total,
        message_limit=bounded_limit,
        message_offset=bounded_offset,
        summary=ConversationSummaryRead.model_validate(summary) if summary else None,
    )


@router.post("/tenants/{tenant_id}/test-conversations/{conversation_id}/messages")
def send_test_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    session_scope_factory: Callable[[], AbstractContextManager[Session]] = Depends(get_session_scope_factory),
) -> StreamingResponse:
    # This `db` (from `Depends(get_db)`) is deliberately used for nothing
    # but this one pre-stream check — it is created and closed correctly
    # and promptly by `get_db`'s normal contract, because this part of the
    # route runs synchronously, before the route function returns anything.
    conversation = _get_conversation_or_404(conversation_id, ctx, db)
    if conversation.status != ConversationStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This conversation is no longer active.")

    provider = _resolve_provider_or_500(settings)

    def sync_event_stream() -> Generator[str, None, None]:
        # A SEPARATE session, deliberately not the `db` above: `Depends()`'s
        # own cleanup fires as soon as this route function returns the
        # StreamingResponse *object*, before this generator body has run at
        # all (see `app.db.session.get_db`'s docstring) — so a session tied
        # to that dependency would already be closed by the time any of
        # this runs. Holding `session_scope_factory()` open for this
        # generator's entire lifetime instead means the exact same explicit
        # create → commit-or-rollback → close contract as every other
        # route applies here too, and it applies deterministically at this
        # generator's true end — on normal completion, on a handled
        # `ConversationError`, on any other exception, or when this
        # generator's own `.close()` is called (see `event_stream` below
        # for why that call is guaranteed even on a real client disconnect,
        # unlike relying on Starlette's default handling for a *sync*
        # generator passed straight to `StreamingResponse`).
        with session_scope_factory() as stream_db:
            orchestrator = ConversationOrchestrator(
                stream_db,
                tenant_id=ctx.tenant_id,
                provider=provider,
                retrieval_limit=settings.retrieval_result_limit,
                max_context_chars=settings.max_conversation_context_chars,
                # Known Phase 4 limitation (documented in docs/api.md): the
                # orchestrator itself has no way to notice a disconnect
                # mid-turn and cut its own work short — the mock provider
                # streams effectively instantly, so the cost of finishing
                # server-side after a disconnect is negligible. A real
                # (slow, network-bound) provider in a later phase should
                # thread a real disconnect check through here. This is
                # independent of *session* cleanup, which `event_stream`
                # below guarantees regardless of whether the orchestrator
                # itself ever notices anything.
                is_disconnected=lambda: False,
            )
            try:
                for event in orchestrator.submit_message(
                    conversation_id, content=payload.content, idempotency_key=payload.idempotency_key
                ):
                    yield _format_sse(event)
            except ConversationError as exc:
                code = getattr(exc, "code", "conversation_error")
                yield _format_sse({"event": "response.error", "data": {"code": code, "message": str(exc)}})

    # Deliberately NOT `StreamingResponse(sync_event_stream(), ...)`: passing
    # a *sync* generator straight to `StreamingResponse` looks correct and
    # handles the happy path fine, but Starlette wraps it in
    # `iterate_in_threadpool`, which never calls `.close()` on it under any
    # circumstance — including a real client disconnect, confirmed live, not
    # just reasoned about (see `stream_sync_generator`'s docstring for the
    # full mechanism). `stream_sync_generator` is the fix: it adapts the sync
    # generator into a genuinely async one, so a cancelled task (a real
    # disconnect) reaches its own `finally` and deterministically closes
    # `sync_event_stream()` — which runs `session_scope_factory()`'s own
    # `__exit__` (commit-or-rollback, then close) — before anything is
    # allowed to finish unwinding.
    return StreamingResponse(
        stream_sync_generator(sync_event_stream()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post(
    "/tenants/{tenant_id}/test-conversations/{conversation_id}/complete",
    response_model=CompleteConversationResponse,
)
def complete_test_conversation(
    conversation_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CompleteConversationResponse:
    _get_conversation_or_404(conversation_id, ctx, db)
    provider = _resolve_provider_or_500(settings)
    orchestrator = ConversationOrchestrator(db, tenant_id=ctx.tenant_id, provider=provider)
    try:
        conversation, summary = orchestrator.complete_conversation(conversation_id)
    except ConversationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CompleteConversationResponse(
        conversation=ConversationRead.model_validate(conversation),
        summary=ConversationSummaryRead.model_validate(summary),
    )

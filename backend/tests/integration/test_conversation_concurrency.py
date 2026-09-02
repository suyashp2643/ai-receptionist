"""PostgreSQL multi-connection integration tests for the Phase 4
conversation engine.

These exist specifically because three genuine production bugs — a row
lock held across a streaming provider call, a per-request connection leak,
and a sequence-number collision under `autoflush=False` — were found only
by testing against the real dev server with real, independently pooled
connections. The 255-test unit suite passed at every stage those bugs were
present, because `tests/conftest.py`'s `db_backed_client` fixture shares
one SQLAlchemy session across every request in a test, collapsing what
would be several independently-pooled connections in production into one.
See docs/architecture.md and docs/security.md for the full writeup.

Every test in this module uses `real_client` (see `conftest.py`): a
`TestClient` with no dependency override, so each HTTP call resolves the
application's real `get_db` and gets a genuinely fresh session on a
genuinely fresh pooled connection — exactly like production. `pytest -m
multiconn` selects just this module; plain `pytest -q` from `backend/`
includes it (it is never filtered out) whenever `DATABASE_URL` is
configured, per the standing rule that these tests must not be silently
skipped in a database-configured environment.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from app.ai.providers.base import ProviderError
from app.ai.providers.mock import MockProvider
from app.db.session import get_session_factory
from sqlalchemy import text

from tests.integration.conftest import held_locks_on, idle_in_transaction_count
from tests.integration.helpers import (
    get_conversation,
    parse_sse,
    register_tenant,
    send_message,
    setup_active_receptionist,
    start_conversation,
)

pytestmark = pytest.mark.multiconn


@pytest.fixture()
def executor():
    pool = ThreadPoolExecutor(max_workers=8)
    yield pool
    # `cancel_futures` so a genuine deadlock regression doesn't also hang
    # fixture teardown — the point of this suite is to fail loudly and
    # quickly on that, not to block the test run trying to be tidy about it.
    pool.shutdown(wait=False, cancel_futures=True)


def _sequence_numbers(conversation_detail: dict) -> list[int]:
    return [m["sequence_number"] for m in conversation_detail["messages"]]


class TestRowLockAcrossStreaming:
    """Defect A: the row lock from `get_for_update` used to be held for the
    entire streaming phase (nothing ever committed to release it), so a
    second message to the same conversation blocked forever."""

    def test_three_sequential_messages_each_complete_within_a_bounded_timeout(
        self, real_client, executor, cleanup_tenants, multiconn_engine
    ):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="lockA")
        receptionist_id = setup_active_receptionist(real_client, headers, tenant_id)
        conversation_id = start_conversation(real_client, headers, tenant_id, receptionist_id)

        for i in range(3):
            response, events = send_message(
                executor, real_client, tenant_id, conversation_id, headers, f"message number {i}", timeout=10
            )
            assert response.status_code == 200, response.text
            event_names = [e["event"] for e in events]
            assert "response.completed" in event_names, event_names
            assert "conversation.updated" in event_names, event_names
            assert "response.error" not in event_names, events

        # No lock from any of the three requests should still be held.
        assert held_locks_on(multiconn_engine, table="conversations") == 0
        assert idle_in_transaction_count(multiconn_engine) == 0


class TestConnectionLeak:
    """Defect B: `expire_on_commit` meant a post-commit attribute read
    silently reopened a transaction nothing would ever close."""

    def test_no_request_leaves_an_idle_in_transaction_connection(
        self, real_client, executor, cleanup_tenants, multiconn_engine
    ):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="leakB")
        receptionist_id = setup_active_receptionist(real_client, headers, tenant_id)
        conversation_id = start_conversation(real_client, headers, tenant_id, receptionist_id)

        baseline_idle_in_txn = idle_in_transaction_count(multiconn_engine)
        baseline_checked_out = multiconn_engine.pool.checkedout()

        for i in range(5):
            response, events = send_message(
                executor, real_client, tenant_id, conversation_id, headers, f"grounding check {i}", timeout=10
            )
            assert response.status_code == 200, response.text
            # Observable database behavior, not an implementation internal:
            # immediately after each fully-consumed request, nothing should
            # be sitting on an open transaction.
            assert idle_in_transaction_count(multiconn_engine) == baseline_idle_in_txn, (
                f"request {i} left a connection idle-in-transaction"
            )
            # The pool's own checked-out counter, checked immediately with
            # no polling/sleep: the streaming route now holds its session
            # open via an explicit `with session_scope_factory() as
            # stream_db:` for the generator's entire lifetime and closes it
            # deterministically when that block exits — by the time
            # `real_client.post(...)` has returned (TestClient fully drains
            # the streamed body before returning), that `with` block has
            # already exited and the connection has already been returned.
            # No `time.sleep`/polling loop and no `gc.collect()` — if this
            # ever regresses to depending on garbage collection instead,
            # this assertion fails immediately and unconditionally.
            assert multiconn_engine.pool.checkedout() == baseline_checked_out, (
                f"request {i} did not return its connection to the pool immediately"
            )


class TestSequenceNumberCollision:
    """Defect C: `next_sequence_number()` re-queried `MAX(...)` more than
    once per uncommitted transaction; with `autoflush=False`, persisting a
    tool-role message and the assistant message in the same transaction
    handed out the same number twice, caught only by the unique
    constraint — surfaced to a real client as a truncated SSE stream."""

    def test_tool_and_assistant_messages_get_unique_increasing_sequence_numbers(
        self, real_client, executor, cleanup_tenants, multiconn_engine
    ):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="seqC")
        receptionist_id = setup_active_receptionist(real_client, headers, tenant_id, with_tool_trigger=True)
        conversation_id = start_conversation(real_client, headers, tenant_id, receptionist_id)

        response, events = send_message(
            executor, real_client, tenant_id, conversation_id, headers, "What are your hours?", timeout=10
        )
        assert response.status_code == 200, response.text
        event_names = [e["event"] for e in events]
        assert "tool.completed" in event_names, "test setup did not actually trigger a tool call: " + str(event_names)
        assert "response.completed" in event_names
        completed = next(e["data"] for e in events if e["event"] == "response.completed")
        assert completed["message_id"] != "None"
        uuid.UUID(completed["message_id"])  # must be a real UUID, not the literal string "None"

        detail = get_conversation(real_client, tenant_id, conversation_id, headers)
        sequence_numbers = _sequence_numbers(detail)
        assert len(sequence_numbers) == len(set(sequence_numbers)), f"duplicate sequence numbers: {sequence_numbers}"
        assert sequence_numbers == sorted(sequence_numbers), f"not strictly increasing: {sequence_numbers}"
        assert sequence_numbers == list(range(len(sequence_numbers))), sequence_numbers

        # Reload twice more and confirm the order is stable, not an
        # artifact of a single lucky read.
        for _ in range(2):
            reloaded = get_conversation(real_client, tenant_id, conversation_id, headers)
            assert _sequence_numbers(reloaded) == sequence_numbers

        # Directly confirm the database itself never accepted a duplicate —
        # not just that the API's own ordering looks fine.
        with multiconn_engine.connect() as conn:
            distinct_count, total_count = conn.execute(
                text(
                    "SELECT count(DISTINCT sequence_number), count(*) FROM conversation_messages "
                    "WHERE conversation_id = :cid"
                ),
                {"cid": conversation_id},
            ).one()
        assert distinct_count == total_count


class TestIdempotentReplay:
    def test_duplicate_submission_via_separate_connections_does_not_duplicate_messages(
        self, real_client, executor, cleanup_tenants, multiconn_engine
    ):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="idemD")
        receptionist_id = setup_active_receptionist(real_client, headers, tenant_id)
        conversation_id = start_conversation(real_client, headers, tenant_id, receptionist_id)
        idempotency_key = f"multiconn-idem-{uuid.uuid4().hex}"

        first_response, first_events = send_message(
            executor, real_client, tenant_id, conversation_id, headers, "Hello there",
            idempotency_key=idempotency_key, timeout=10,
        )
        assert first_response.status_code == 200, first_response.text
        first_completed = next(e["data"] for e in first_events if e["event"] == "response.completed")

        detail_after_first = get_conversation(real_client, tenant_id, conversation_id, headers)
        assert detail_after_first["message_total"] == 2  # user + assistant

        # A genuinely separate request/connection replays the same key.
        second_response, second_events = send_message(
            executor, real_client, tenant_id, conversation_id, headers, "Hello there",
            idempotency_key=idempotency_key, timeout=10,
        )
        assert second_response.status_code == 200, second_response.text
        second_completed = next(e["data"] for e in second_events if e["event"] == "response.completed")

        assert second_completed["message_id"] == first_completed["message_id"]
        assert second_completed.get("replay") is True

        detail_after_second = get_conversation(real_client, tenant_id, conversation_id, headers)
        assert detail_after_second["message_total"] == 2, "the replay must not have inserted any new message"
        assert _sequence_numbers(detail_after_second) == _sequence_numbers(detail_after_first)

        assert idle_in_transaction_count(multiconn_engine) == 0


class TestConcurrentSubmission:
    """Defect/behavior E. Documented, intended behavior: two simultaneous
    submissions to the same conversation serialize at the row lock —
    both complete successfully, in some order, with unique and correctly
    ordered sequence numbers. Neither deadlocks, corrupts state, nor
    produces a truncated SSE response. Uses a receptionist with an empty
    qualification schema so the test isolates locking/sequencing behavior
    from the separate (and out of scope here) question of merging
    concurrent qualification-field updates."""

    def test_two_concurrent_messages_both_complete_without_corruption(
        self, real_client, executor, cleanup_tenants, multiconn_engine
    ):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="concE")
        receptionist_id = setup_active_receptionist(real_client, headers, tenant_id)
        conversation_id = start_conversation(real_client, headers, tenant_id, receptionist_id)

        body_a = {"content": "First concurrent message"}
        body_b = {"content": "Second concurrent message"}
        future_a = executor.submit(
            real_client.post,
            f"/api/v1/tenants/{tenant_id}/test-conversations/{conversation_id}/messages",
            json=body_a,
            headers=headers,
        )
        future_b = executor.submit(
            real_client.post,
            f"/api/v1/tenants/{tenant_id}/test-conversations/{conversation_id}/messages",
            json=body_b,
            headers=headers,
        )
        response_a = future_a.result(timeout=20)
        response_b = future_b.result(timeout=20)

        assert response_a.status_code == 200, response_a.text
        assert response_b.status_code == 200, response_b.text

        for response in (response_a, response_b):
            event_names = [e["event"] for e in parse_sse(response.text)]
            assert "response.completed" in event_names, event_names
            assert "conversation.updated" in event_names, event_names
            assert "response.error" not in event_names, event_names

        detail = get_conversation(real_client, tenant_id, conversation_id, headers)
        sequence_numbers = _sequence_numbers(detail)
        assert len(sequence_numbers) == 4, "expected exactly 2 user + 2 assistant messages"
        assert len(sequence_numbers) == len(set(sequence_numbers)), f"duplicate sequence numbers: {sequence_numbers}"
        assert sequence_numbers == list(range(4)), sequence_numbers

        contents = [m["content"] for m in detail["messages"] if m["role"] == "user"]
        assert set(contents) == {"First concurrent message", "Second concurrent message"}

        assert held_locks_on(multiconn_engine, table="conversations") == 0
        assert idle_in_transaction_count(multiconn_engine) == 0


class TestFailureRecovery:
    def test_provider_failure_leaves_a_safe_retryable_state_and_releases_the_connection(
        self, real_client, executor, cleanup_tenants, multiconn_engine
    ):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="failF")
        receptionist_id = setup_active_receptionist(real_client, headers, tenant_id)
        conversation_id = start_conversation(real_client, headers, tenant_id, receptionist_id)
        idempotency_key = f"multiconn-retry-{uuid.uuid4().hex}"

        class _ForcedFailure(ProviderError):
            code = "multiconn_test_forced_failure"

        def _raise(*_args, **_kwargs):
            raise _ForcedFailure("forced failure for integration test")

        baseline_checked_out = multiconn_engine.pool.checkedout()
        with patch.object(MockProvider, "stream", side_effect=_raise):
            response, events = send_message(
                executor, real_client, tenant_id, conversation_id, headers, "trigger a failure",
                idempotency_key=idempotency_key, timeout=10,
            )
        assert response.status_code == 200, response.text  # SSE stream itself is a normal HTTP 200
        event_names = [e["event"] for e in events]
        assert "response.error" in event_names, event_names
        error_data = next(e["data"] for e in events if e["event"] == "response.error")
        assert error_data["code"] == "multiconn_test_forced_failure"

        detail = get_conversation(real_client, tenant_id, conversation_id, headers)
        assert detail["conversation"]["status"] == "active"
        assert detail["conversation"]["last_error_code"] == "multiconn_test_forced_failure"
        assert detail["message_total"] == 1  # only the user message — no assistant message for the failed turn

        # The connection/transaction used for the failed attempt must have
        # been released, not left idle-in-transaction — and, checked
        # immediately with no polling, actually returned to the pool.
        assert idle_in_transaction_count(multiconn_engine) == 0
        assert held_locks_on(multiconn_engine, table="conversations") == 0
        assert multiconn_engine.pool.checkedout() == baseline_checked_out

        # A permitted retry (same idempotency key, provider no longer
        # patched) must succeed without duplicating the original user message.
        retry_response, retry_events = send_message(
            executor, real_client, tenant_id, conversation_id, headers, "trigger a failure",
            idempotency_key=idempotency_key, timeout=10,
        )
        assert retry_response.status_code == 200, retry_response.text
        retry_event_names = [e["event"] for e in retry_events]
        assert "response.completed" in retry_event_names, retry_event_names

        final_detail = get_conversation(real_client, tenant_id, conversation_id, headers)
        assert final_detail["message_total"] == 2  # the original user message + the retry's assistant message
        user_messages = [m for m in final_detail["messages"] if m["role"] == "user"]
        assert len(user_messages) == 1, "the retry must not have inserted a second user message"
        sequence_numbers = _sequence_numbers(final_detail)
        assert sequence_numbers == list(range(len(sequence_numbers)))


class TestGeneratorCloseCleanup:
    """SSE disconnect limitation: a client disconnecting mid-stream closes
    the underlying generator (`GeneratorExit`), which is not a subclass of
    `Exception` and so is not caught by `submit_message`'s own
    `except Exception: rollback` safety net. Two complementary properties,
    each with its own test below: (1) the orchestrator never yields while
    holding the conversation row lock, so a disconnect can never catch it
    mid-lock; (2) the route's own `session_scope_factory()` — the thing
    that actually owns and closes the session — closes deterministically
    even when the generator using it is closed from outside, nested
    exactly as `send_test_message`'s real `event_stream` nests it."""

    def test_closing_the_generator_after_the_first_event_leaves_no_lock_or_transaction(
        self, cleanup_tenants, multiconn_engine, real_client
    ):
        """Orchestrator-level property: no `get_for_update()` is ever
        followed by a `yield` before its matching commit/rollback, proven
        directly against the orchestrator with its own manually-managed
        session (deliberately not `session_scope` here — this test is about
        the orchestrator's locking discipline, not session ownership)."""
        from app.ai.orchestrator import ConversationOrchestrator
        from app.ai.providers.factory import get_provider
        from app.config import get_settings

        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="genclose")
        receptionist_id = setup_active_receptionist(real_client, headers, tenant_id)

        settings = get_settings()
        session_factory = get_session_factory()
        assert session_factory is not None
        db = session_factory()
        try:
            orchestrator = ConversationOrchestrator(
                db,
                tenant_id=uuid.UUID(tenant_id),
                provider=get_provider(settings),
                retrieval_limit=settings.retrieval_result_limit,
                max_context_chars=settings.max_conversation_context_chars,
            )
            conversation = orchestrator.start_conversation(receptionist_id=uuid.UUID(receptionist_id))
            db.commit()

            generator = orchestrator.submit_message(conversation.id, content="hello")
            first_event = next(generator)
            assert first_event["event"] == "message.started"
            generator.close()
        finally:
            db.close()

        assert idle_in_transaction_count(multiconn_engine) == 0
        assert held_locks_on(multiconn_engine, table="conversations") == 0

    def test_closing_the_route_level_generator_early_returns_its_session_to_the_pool(
        self, real_client, cleanup_tenants, multiconn_engine
    ):
        """Session-ownership property: reproduces `send_test_message`'s
        exact `event_stream` composition — `with session_scope_factory()
        as stream_db: orchestrator = ...; for event in
        orchestrator.submit_message(...): yield ...` — using the real,
        unmodified `session_scope` (no test override), and closes the
        OUTER generator early. Proves `session_scope`'s `with`-block
        cleanup fires even nested inside a generator that is itself being
        closed from outside, checked against the real connection pool —
        not an internal call-count — with no polling and no `gc.collect()`."""
        from app.ai.orchestrator import ConversationOrchestrator
        from app.ai.providers.factory import get_provider
        from app.config import get_settings
        from app.db.session import session_scope

        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="routegenclose")
        receptionist_id = setup_active_receptionist(real_client, headers, tenant_id)
        settings = get_settings()

        with session_scope() as setup_db:
            setup_orchestrator = ConversationOrchestrator(
                setup_db,
                tenant_id=uuid.UUID(tenant_id),
                provider=get_provider(settings),
                retrieval_limit=settings.retrieval_result_limit,
                max_context_chars=settings.max_conversation_context_chars,
            )
            conversation = setup_orchestrator.start_conversation(receptionist_id=uuid.UUID(receptionist_id))
            # Read while still inside the block: `session_scope` now really
            # does `.close()` the session on exit (that's the whole point
            # of this fix), which detaches `conversation` from it — reading
            # `.id` afterward would itself raise `DetachedInstanceError`.
            conversation_id = conversation.id

        baseline_checked_out = multiconn_engine.pool.checkedout()

        def route_style_event_stream():
            with session_scope() as stream_db:
                orchestrator = ConversationOrchestrator(
                    stream_db,
                    tenant_id=uuid.UUID(tenant_id),
                    provider=get_provider(settings),
                    retrieval_limit=settings.retrieval_result_limit,
                    max_context_chars=settings.max_conversation_context_chars,
                )
                yield from orchestrator.submit_message(conversation_id, content="hello")

        generator = route_style_event_stream()
        first_event = next(generator)
        assert first_event["event"] == "message.started"
        generator.close()

        assert idle_in_transaction_count(multiconn_engine) == 0
        assert held_locks_on(multiconn_engine, table="conversations") == 0
        assert multiconn_engine.pool.checkedout() == baseline_checked_out, (
            "the route-level generator's session was not returned to the pool when closed early"
        )


class TestNormalRouteSessionLifecycle:
    """`app.db.session.get_db` (the FastAPI dependency every *non*-streaming
    route uses) has its own explicit contract too, unchanged by the
    streaming-route fix above — proven here against a real ordinary GET,
    through real HTTP, with no polling and no `gc.collect()`."""

    def test_closes_after_a_successful_request(self, real_client, executor, cleanup_tenants, multiconn_engine):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="normclose")
        baseline_checked_out = multiconn_engine.pool.checkedout()

        response = executor.submit(
            real_client.get, f"/api/v1/tenants/{tenant_id}/test-conversations", headers=headers
        ).result(timeout=10)

        assert response.status_code == 200, response.text
        assert idle_in_transaction_count(multiconn_engine) == 0
        assert multiconn_engine.pool.checkedout() == baseline_checked_out

    def test_rolls_back_and_closes_after_an_exception(
        self, real_client, executor, cleanup_tenants, multiconn_engine
    ):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="normexc")
        baseline_checked_out = multiconn_engine.pool.checkedout()

        # A nonexistent conversation id makes the route raise HTTPException
        # (404) from inside `_get_conversation_or_404` — a real exception
        # propagating up through `Depends(get_db)`'s exit stack, not a
        # successful return.
        response = executor.submit(
            real_client.get,
            f"/api/v1/tenants/{tenant_id}/test-conversations/{uuid.uuid4()}",
            headers=headers,
        ).result(timeout=10)

        assert response.status_code == 404, response.text
        assert idle_in_transaction_count(multiconn_engine) == 0
        assert multiconn_engine.pool.checkedout() == baseline_checked_out

    def test_five_sequential_normal_requests_never_grow_checked_out_connections(
        self, real_client, executor, cleanup_tenants, multiconn_engine
    ):
        headers, tenant_id = register_tenant(real_client, cleanup_tenants, label="normseq")
        baseline_checked_out = multiconn_engine.pool.checkedout()

        for i in range(5):
            response = executor.submit(
                real_client.get, f"/api/v1/tenants/{tenant_id}/test-conversations", headers=headers
            ).result(timeout=10)
            assert response.status_code == 200, response.text
            assert multiconn_engine.pool.checkedout() == baseline_checked_out, (
                f"request {i} left a connection checked out"
            )

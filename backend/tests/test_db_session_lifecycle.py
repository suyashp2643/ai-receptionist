"""Fast unit tests for the explicit session-ownership contract in
`app.db.session.session_scope()` / `get_db()` — see docs/architecture.md's
"Explicit session ownership" section for the full design writeup.

These tests use a mock `Session` (no real database, no `_db_engine`
fixture, no network) specifically so they can assert exactly what
production code calls, in what order, on every exit path — including
`GeneratorExit` (the SSE-disconnect case) and a failure during commit or
rollback itself — deterministically, in a single synchronous assertion,
with zero reliance on garbage collection, reference counting, or any
Python-implementation-specific object-finalization timing. The
real-database, real-HTTP proof that this contract holds end-to-end lives
in `tests/integration/test_conversation_concurrency.py`.
"""

from unittest.mock import MagicMock, patch

import pytest
from app.db import session as db_session_module
from sqlalchemy.orm import Session


def _mock_factory() -> tuple[MagicMock, MagicMock]:
    mock_db = MagicMock(spec=Session)
    factory = MagicMock(return_value=mock_db)
    return factory, mock_db


class TestSessionScopeOwnership:
    def test_commits_and_closes_on_success(self):
        factory, mock_db = _mock_factory()
        with patch.object(db_session_module, "get_session_factory", return_value=factory):
            with db_session_module.session_scope() as db:
                assert db is mock_db
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()
        mock_db.close.assert_called_once()
        # Ordering matters, not just call counts: close() must be the last
        # thing that happens, after commit() has already run.
        assert [c[0] for c in mock_db.method_calls] == ["commit", "close"]

    def test_rolls_back_and_closes_on_exception(self):
        factory, mock_db = _mock_factory()
        with pytest.raises(ValueError, match="boom"):
            with patch.object(db_session_module, "get_session_factory", return_value=factory):
                with db_session_module.session_scope() as db:
                    assert db is mock_db
                    raise ValueError("boom")
        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()
        assert [c[0] for c in mock_db.method_calls] == ["rollback", "close"]

    def test_rolls_back_and_closes_on_generator_exit(self):
        """Simulates an SSE client disconnect: whatever is using this
        session is itself a generator that gets `.close()`d early, which
        Python delivers as a `GeneratorExit` thrown in at the currently
        suspended `yield` — not a subclass of `Exception`, which is
        exactly why `session_scope` deliberately catches `BaseException`
        instead."""
        factory, mock_db = _mock_factory()

        def user_generator():
            with patch.object(db_session_module, "get_session_factory", return_value=factory):
                with db_session_module.session_scope() as db:
                    yield db  # suspended here; gen.close() below resumes this with GeneratorExit

        gen = user_generator()
        first = next(gen)
        assert first is mock_db
        gen.close()

        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    def test_close_still_happens_if_rollback_itself_raises(self):
        """The `finally` is unconditional on top of the except-and-rollback
        branch: even a broken rollback must not leak the connection."""
        factory, mock_db = _mock_factory()
        mock_db.rollback.side_effect = RuntimeError("rollback itself failed")
        with pytest.raises(RuntimeError, match="rollback itself failed"):
            with patch.object(db_session_module, "get_session_factory", return_value=factory):
                with db_session_module.session_scope():
                    raise ValueError("original failure")
        mock_db.close.assert_called_once()

    def test_rolls_back_and_closes_if_commit_itself_raises(self):
        """A failure during the success-path commit is still a failure —
        it must roll back (not leave a half-committed transaction open)
        and still close."""
        factory, mock_db = _mock_factory()
        mock_db.commit.side_effect = RuntimeError("commit failed")
        with pytest.raises(RuntimeError, match="commit failed"):
            with patch.object(db_session_module, "get_session_factory", return_value=factory):
                with db_session_module.session_scope():
                    pass  # success path — but commit() itself will raise
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    def test_get_db_delegates_to_session_scope_with_an_identical_contract(self):
        """get_db is FastAPI's `Depends(..., yield)` adapter over
        session_scope, not a second implementation of the same contract —
        this proves it actually delegates rather than having drifted."""
        factory, mock_db = _mock_factory()
        with patch.object(db_session_module, "get_session_factory", return_value=factory):
            gen = db_session_module.get_db()
            db = next(gen)
            assert db is mock_db
            with pytest.raises(StopIteration):
                next(gen)
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    def test_get_db_rolls_back_and_closes_when_the_caller_raises(self):
        factory, mock_db = _mock_factory()
        with patch.object(db_session_module, "get_session_factory", return_value=factory):
            gen = db_session_module.get_db()
            next(gen)
            with pytest.raises(ValueError, match="caller failed"):
                gen.throw(ValueError("caller failed"))
        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestOrchestratorAndRepositoriesNeverCloseASessionTheyDidNotCreate:
    """Static, source-level enforcement of the ownership boundary: the
    orchestrator and every repository are always handed a session someone
    else created (session_scope, ultimately) and must never call `.close()`
    on it — only the code that created a session may close it. A future
    change that violated this would be caught here immediately, rather
    than only manifesting as an intermittent connection-pool leak under
    real concurrent load."""

    def test_orchestrator_module_never_calls_close(self):
        import inspect

        from app.ai import orchestrator as orchestrator_module

        source = inspect.getsource(orchestrator_module)
        assert ".close(" not in source, (
            "ConversationOrchestrator must never close a session it did not create — "
            "session lifecycle is owned exclusively by app.db.session.session_scope()."
        )

    def test_repository_modules_never_call_close(self):
        import inspect

        from app.repositories import base as repo_base_module
        from app.repositories import conversation as repo_conversation_module

        for module in (repo_base_module, repo_conversation_module):
            source = inspect.getsource(module)
            assert ".close(" not in source, f"{module.__name__} must never close a session it did not create"

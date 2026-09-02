"""Fast unit tests for `app.api.v1.conversations.stream_sync_generator` —
the adapter that makes a client disconnect during
`POST .../test-conversations/{id}/messages` reach deterministic cleanup,
instead of orphaning the underlying sync generator (and the database
session it owns via `session_scope`) forever.

Why this needs its own test, separate from the multi-connection
integration suite: this exact bug — Starlette's `iterate_in_threadpool`
(used automatically for a *sync* generator passed straight to
`StreamingResponse`) never calls `.close()` on it under any circumstance,
confirmed by reading its source — was found live, against a real TCP
client, specifically because `TestClient`'s in-process ASGI transport runs
a fast (mock-provider-backed) streaming response to completion before a
client ever gets a chance to disconnect mid-stream; there is no reliable
way to reproduce a slow-enough disconnect through it. Testing
`stream_sync_generator` directly, with a trivial generator standing in for
`sync_event_stream`'s real `session_scope`-owning body, proves the exact
mechanism (an early `.aclose()` on the async wrapper — what a cancelled
Starlette task ultimately delivers — closes the wrapped sync generator)
without needing a database, a real client, or exact-enough timing at all.
"""

import pytest
from app.api.v1.conversations import stream_sync_generator


def _tracking_generator():
    """Stands in for `sync_event_stream`'s real body (a `with
    session_scope_factory() as ...: ... yield ...` block) — records
    whether `finally` ran (the stand-in for the session being released)
    and exactly how far the generator was resumed."""
    state = {"closed": False, "yielded": []}

    def gen():
        try:
            state["yielded"].append("a")
            yield "a"
            state["yielded"].append("b")
            yield "b"
            state["yielded"].append("c")
            yield "c"
        finally:
            state["closed"] = True

    return gen(), state


class TestStreamSyncGeneratorCancellation:
    async def test_drains_every_value_and_closes_on_normal_completion(self):
        sync_gen, state = _tracking_generator()
        collected = [chunk async for chunk in stream_sync_generator(sync_gen)]
        assert collected == ["a", "b", "c"]
        assert state["closed"] is True

    async def test_closing_the_async_wrapper_early_closes_the_sync_generator(self):
        """The direct regression test for the live-discovered bug: closing
        the async generator early — exactly what happens to the real
        `StreamingResponse` body iterator when Starlette cancels the task
        driving it on a client disconnect — must close the underlying sync
        generator there and then, not abandon it mid-stream forever."""
        sync_gen, state = _tracking_generator()
        async_gen = stream_sync_generator(sync_gen)

        first = await async_gen.__anext__()
        assert first == "a"
        assert state["closed"] is False  # still mid-stream — nothing should have closed yet

        await async_gen.aclose()

        assert state["closed"] is True
        assert state["yielded"] == ["a"], "the sync generator must not have been resumed after being closed"

    async def test_an_exception_from_the_sync_generator_still_propagates_and_closes(self):
        events: list[str] = []

        def gen():
            try:
                yield "a"
                raise ValueError("boom from inside the sync generator")
            finally:
                events.append("closed")

        async_gen = stream_sync_generator(gen())
        first = await async_gen.__anext__()
        assert first == "a"

        with pytest.raises(ValueError, match="boom from inside the sync generator"):
            await async_gen.__anext__()
        assert events == ["closed"]

    async def test_empty_generator_yields_nothing_and_still_closes(self):
        state = {"closed": False}

        def gen():
            try:
                return
                yield  # pragma: no cover - unreachable, only makes this a generator
            finally:
                state["closed"] = True

        collected = [chunk async for chunk in stream_sync_generator(gen())]
        assert collected == []
        assert state["closed"] is True

"""Rate limiting for the public widget API. `RateLimiter` is a small
Protocol so a future Redis-backed adapter can be dropped in without
touching call sites; `InMemoryRateLimiter` is the only implementation
Phase 5 ships, and it is explicitly single-process only — see its
docstring. Nothing here is applied to the authenticated dashboard API.
"""

import time
from dataclasses import dataclass
from threading import Lock
from typing import Protocol


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimiter(Protocol):
    def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult: ...
    def reset(self, key: str | None = None) -> None:
        """Clears one key, or (if key is None) every key — tests use this
        to get an isolated limiter between cases without recreating one."""
        ...


@dataclass
class _Bucket:
    window_started_at: float
    count: int


class InMemoryRateLimiter:
    """Fixed-window counter per key, held in process memory.

    Single-process only by design: this does NOT coordinate across multiple
    backend worker processes/instances, so a deployment running more than
    one worker gets a limit that is effectively `limit * worker_count`. That
    is an accepted, documented limitation for Phase 5's zero-cost scope
    (see docs/security.md) — a Redis-backed implementation of the same
    `RateLimiter` Protocol is the intended upgrade path, not a rewrite of
    call sites.

    Expired buckets are evicted lazily (on the next `check` call that
    touches an expired key, and via periodic `_sweep`) so memory does not
    grow unboundedly across a long-running process.
    """

    def __init__(self, *, sweep_interval_seconds: int = 300) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()
        self._sweep_interval_seconds = sweep_interval_seconds
        self._last_swept_at = time.monotonic()

    def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        now = time.monotonic()
        with self._lock:
            self._maybe_sweep(now, window_seconds)
            bucket = self._buckets.get(key)
            if bucket is None or (now - bucket.window_started_at) >= window_seconds:
                bucket = _Bucket(window_started_at=now, count=0)
                self._buckets[key] = bucket

            elapsed = now - bucket.window_started_at
            retry_after = max(0, int(window_seconds - elapsed))

            if bucket.count >= limit:
                return RateLimitResult(
                    allowed=False, limit=limit, remaining=0, retry_after_seconds=retry_after
                )

            bucket.count += 1
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=max(0, limit - bucket.count),
                retry_after_seconds=retry_after,
            )

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)

    def _maybe_sweep(self, now: float, window_seconds: int) -> None:
        if (now - self._last_swept_at) < self._sweep_interval_seconds:
            return
        self._last_swept_at = now
        expired = [k for k, b in self._buckets.items() if (now - b.window_started_at) >= window_seconds]
        for k in expired:
            self._buckets.pop(k, None)


_default_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Process-wide singleton used by the public widget API dependencies.
    Tests should construct their own `InMemoryRateLimiter()` instance (or
    call `.reset()` on this one) rather than relying on cross-test state."""
    return _default_limiter

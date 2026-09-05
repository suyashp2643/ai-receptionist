"""Exponential backoff with full jitter (the AWS-recommended strategy —
uniformly random between 0 and the exponential ceiling, not a fixed delay
plus a small random offset) — avoids every retrying delivery for a
down receiver converging on the same retry instants."""

from __future__ import annotations

import random


def compute_backoff_seconds(attempt_count: int, *, base_seconds: float, max_seconds: float) -> float:
    """`attempt_count` is 1-indexed (the attempt that just failed). Returns
    the number of seconds to wait before the NEXT attempt becomes
    eligible."""
    ceiling = min(max_seconds, base_seconds * (2 ** max(0, attempt_count - 1)))
    return random.uniform(0, ceiling)

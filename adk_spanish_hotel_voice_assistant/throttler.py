"""Sliding-window rate limiter for webhook endpoints (abuse mitigation).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import DefaultDict, List


class SlidingWindowLimiter:
    """Allow up to `limit` events per `window_sec` per key (e.g. client IP)."""

    def __init__(self, limit: int, window_sec: float = 60.0) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self._hits: DefaultDict[str, List[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.time()
        cutoff = now - self.window_sec
        bucket = self._hits[key]
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True

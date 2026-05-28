"""Sliding-window rate limiter for webhook endpoints (abuse mitigation).

Per-process only: with multiple Waitress workers or replicas the effective limit
scales roughly with instance count unless a shared store (e.g. Redis) is added.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import DefaultDict, List


class SlidingWindowLimiter:
    """Allow up to ``limit`` events per ``window_sec`` per key (e.g. client IP)."""

    def __init__(
        self,
        limit: int,
        window_sec: float = 60.0,
        *,
        max_keys: int = 10_000,
    ) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self.max_keys = max(1, max_keys)
        self._hits: DefaultDict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _purge_inactive(self, cutoff: float) -> None:
        stale = [key for key, bucket in self._hits.items() if not bucket or bucket[-1] <= cutoff]
        for key in stale:
            del self._hits[key]

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.time()
        cutoff = now - self.window_sec
        with self._lock:
            if len(self._hits) > self.max_keys:
                self._purge_inactive(cutoff)
            bucket = self._hits[key]
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

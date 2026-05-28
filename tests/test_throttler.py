# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""Sliding-window rate limiter."""

import threading

from adk_spanish_hotel_voice_assistant.throttler import SlidingWindowLimiter


def test_limiter_blocks_after_limit():
    limiter = SlidingWindowLimiter(2, window_sec=60.0)
    assert limiter.allow("ip-a") is True
    assert limiter.allow("ip-a") is True
    assert limiter.allow("ip-a") is False


def test_limiter_is_thread_safe_under_contention():
    limiter = SlidingWindowLimiter(50, window_sec=60.0, max_keys=100)
    allowed = []

    def worker():
        for _ in range(20):
            if limiter.allow("shared"):
                allowed.append(1)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(allowed) == 50

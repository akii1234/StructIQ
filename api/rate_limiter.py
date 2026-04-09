"""Thread-safe per-key sliding-window rate limiter."""
from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Sliding window rate limiter.

    Args:
        max_requests: Maximum requests allowed in the window.
        window_seconds: Duration of the sliding window in seconds.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Return True if the request is within quota, False if rate-limited."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                return False
            bucket.append(now)
            return True

    def reset(self, key: str) -> None:
        """Clear all recorded requests for a key (for testing)."""
        with self._lock:
            self._buckets.pop(key, None)

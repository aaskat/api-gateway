"""Rate limiting strategies. Thread-safe, clock-injected for deterministic tests."""

import math
import time
from threading import Lock
from typing import Callable

from pydantic import BaseModel


class RateLimitDecision(BaseModel):
    allowed: bool
    retry_after: int = 0  # ceil seconds until allowed; 0 when allowed


class SlidingWindowLimiter:
    """Sliding-window-log limiter: at most `requests` hits per `window` seconds."""

    def __init__(self, requests: int, window: float, clock: Callable[[], float] = time.monotonic):
        self._requests = requests
        self._window = window
        self._clock = clock
        self._lock = Lock()
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str) -> RateLimitDecision:
        """Atomically evict expired hits, then admit or reject this request."""
        with self._lock:
            now = self._clock()
            cutoff = now - self._window
            hits = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(hits) < self._requests:
                hits.append(now)
                self._hits[key] = hits
                return RateLimitDecision(allowed=True, retry_after=0)
            # Oldest hit must fall out of the window before a slot frees up.
            self._hits[key] = hits
            retry_after = math.ceil(hits[0] + self._window - now)
            return RateLimitDecision(allowed=False, retry_after=retry_after)

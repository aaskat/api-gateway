"""Rate limiting strategies. Thread-safe, clock-injected for deterministic tests."""

import math
import time
from threading import Lock
from typing import Callable

from pydantic import BaseModel


class RateLimitDecision(BaseModel):
    allowed: bool
    retry_after: int = 0  # ceil seconds until allowed; 0 when allowed


class FixedWindowLimiter:
    """Fixed-window limiter: `requests` per aligned [n*window, (n+1)*window) bucket."""

    def __init__(self, requests: int, window: float, clock: Callable[[], float] = time.monotonic):
        self._requests = requests
        self._window = window
        self._clock = clock
        self._lock = Lock()
        self._state: dict[str, tuple[float, int]] = {}  # key -> (window_start, count)

    def check(self, key: str) -> RateLimitDecision:
        """Atomically reset on a new window, then admit or reject this request."""
        with self._lock:
            now = self._clock()
            window_start = (now // self._window) * self._window
            prev_start, count = self._state.get(key, (window_start, 0))
            if prev_start != window_start:
                count = 0  # rolled into a new window
            if count < self._requests:
                self._state[key] = (window_start, count + 1)
                return RateLimitDecision(allowed=True, retry_after=0)
            self._state[key] = (window_start, count)
            retry_after = math.ceil(window_start + self._window - now)
            return RateLimitDecision(allowed=False, retry_after=retry_after)


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

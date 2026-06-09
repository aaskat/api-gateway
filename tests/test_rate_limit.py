"""Tier 2: rate limiters — limit, retry_after, window behavior, concurrency."""

import threading

from gatewaykit.ratelimit import FixedWindowLimiter, SlidingWindowLimiter


class FakeClock:
    def __init__(self, now: float = 0.0):
        self._now = now

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_allows_up_to_limit():
    limiter = SlidingWindowLimiter(3, 60, FakeClock())
    assert [limiter.check("k").allowed for _ in range(3)] == [True, True, True]
    assert limiter.check("k").allowed is False


def test_denied_reports_retry_after():
    limiter = SlidingWindowLimiter(2, 60, FakeClock())
    limiter.check("k")
    limiter.check("k")
    decision = limiter.check("k")
    assert decision.allowed is False
    assert decision.retry_after == 60


def test_window_slides():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(2, 60, clock)
    assert limiter.check("k").allowed is True  # t=0
    clock.advance(30)
    assert limiter.check("k").allowed is True  # t=30 -> 2 in window
    clock.advance(1)
    assert limiter.check("k").allowed is False  # t=31 -> still 2 in [0,30]
    clock.advance(30)
    assert limiter.check("k").allowed is True  # t=61 -> t=0 evicted, 1 in window


def test_keys_are_independent():
    limiter = SlidingWindowLimiter(1, 60, FakeClock())
    assert limiter.check("a").allowed is True
    assert limiter.check("a").allowed is False
    assert limiter.check("b").allowed is True


def test_concurrency_exactly_limit_allowed():
    limiter = SlidingWindowLimiter(10, 60, FakeClock())
    n = 50
    barrier = threading.Barrier(n)
    results = []
    results_lock = threading.Lock()

    def worker():
        barrier.wait()  # all threads contend at once
        decision = limiter.check("shared")
        with results_lock:
            results.append(decision.allowed)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 50
    assert sum(results) == 10  # exactly the limit allowed, no overcount


def test_fixed_allows_up_to_limit():
    limiter = FixedWindowLimiter(3, 60, FakeClock())
    assert [limiter.check("k").allowed for _ in range(3)] == [True, True, True]
    assert limiter.check("k").allowed is False


def test_fixed_denied_reports_retry_after():
    limiter = FixedWindowLimiter(2, 60, FakeClock())
    limiter.check("k")
    limiter.check("k")
    decision = limiter.check("k")
    assert decision.allowed is False
    assert decision.retry_after == 60


def test_fixed_window_resets_at_boundary():
    clock = FakeClock()
    limiter = FixedWindowLimiter(1, 60, clock)
    assert limiter.check("k").allowed is True  # t=0
    clock.advance(59)
    assert limiter.check("k").allowed is False  # t=59, same window
    clock.advance(1)
    assert limiter.check("k").allowed is True  # t=60, new window resets


def test_fixed_keys_are_independent():
    limiter = FixedWindowLimiter(1, 60, FakeClock())
    assert limiter.check("a").allowed is True
    assert limiter.check("a").allowed is False
    assert limiter.check("b").allowed is True


def test_fixed_concurrency_exactly_limit_allowed():
    limiter = FixedWindowLimiter(10, 60, FakeClock())
    n = 50
    barrier = threading.Barrier(n)
    results = []
    results_lock = threading.Lock()

    def worker():
        barrier.wait()
        decision = limiter.check("shared")
        with results_lock:
            results.append(decision.allowed)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 50
    assert sum(results) == 10

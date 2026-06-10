"""Tier 2: RateLimit middleware — strategy select, ip/global bucket, 429 + Retry-After."""

import json

from gatewaykit.config import RateLimit as RateLimitConfig
from gatewaykit.core import RequestContext, Response
from gatewaykit.middleware import RateLimit
from gatewaykit.ratelimit import FixedWindowLimiter, SlidingWindowLimiter


class FakeClock:
    def __init__(self, now: float = 0.0):
        self._now = now

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def config(requests=2, strategy="sliding_window", per="ip") -> RateLimitConfig:
    return RateLimitConfig(requests=requests, window="60s", strategy=strategy, per=per)


def ctx(ip="1.1.1.1") -> RequestContext:
    return RequestContext("GET", "/", {}, b"", ip, route=None, upstream_path="/")


def ok(_ctx) -> Response:
    return Response(200, {}, b"ok")


def test_allows_under_limit():
    mw = RateLimit(config(requests=2), FakeClock())
    assert mw.handle(ctx(), ok).status == 200
    assert mw.handle(ctx(), ok).status == 200


def test_rejects_over_limit_with_429_and_retry_after():
    mw = RateLimit(config(requests=1), FakeClock())
    assert mw.handle(ctx(), ok).status == 200
    resp = mw.handle(ctx(), ok)
    assert resp.status == 429
    assert resp.headers["Retry-After"] == "60"
    assert json.loads(resp.body) == {"error": "rate_limited", "retry_after": 60}


def test_does_not_call_next_when_rejected():
    mw = RateLimit(config(requests=1), FakeClock())
    calls = 0

    def terminal(_ctx):
        nonlocal calls
        calls += 1
        return Response(200, {}, b"")

    assert mw.handle(ctx(), terminal).status == 200  # consumes the single slot
    assert mw.handle(ctx(), terminal).status == 429  # rejected, terminal skipped
    assert calls == 1


def test_per_ip_buckets_independently():
    mw = RateLimit(config(requests=1, per="ip"), FakeClock())
    assert mw.handle(ctx("1.1.1.1"), ok).status == 200
    assert mw.handle(ctx("1.1.1.1"), ok).status == 429
    assert mw.handle(ctx("2.2.2.2"), ok).status == 200  # different ip, own bucket


def test_per_global_shares_one_bucket():
    mw = RateLimit(config(requests=1, per="global"), FakeClock())
    assert mw.handle(ctx("1.1.1.1"), ok).status == 200
    assert mw.handle(ctx("2.2.2.2"), ok).status == 429  # same bucket despite new ip


def test_strategy_select():
    assert isinstance(RateLimit(config(strategy="fixed_window"))._limiter, FixedWindowLimiter)
    assert isinstance(RateLimit(config(strategy="sliding_window"))._limiter, SlidingWindowLimiter)

"""Tier 2: RateLimit middleware — strategy select, ip/global bucket, 429 + Retry-After."""

import http.client
import json

from gatewaykit.config import GatewayConfig, RouteConfig, UpstreamConfig
from gatewaykit.config import RateLimit as RateLimitConfig
from gatewaykit.core import RequestContext, Response
from gatewaykit.middleware import RateLimit, StripPrefix, build_pipeline
from gatewaykit.ratelimit import FixedWindowLimiter, SlidingWindowLimiter
from gatewaykit.server import GatewayServer


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


def route(rate_limit=None, strip=False) -> RouteConfig:
    return RouteConfig(
        path="/svc",
        methods=["GET"],
        strip_prefix=strip,
        upstream=UpstreamConfig(url="http://x"),
        rate_limit=rate_limit,
    )


def test_build_pipeline_includes_rate_limit_when_configured():
    chain = build_pipeline(route(rate_limit=config()))
    assert len(chain) == 1 and isinstance(chain[0], RateLimit)


def test_build_pipeline_omits_rate_limit_when_absent():
    assert build_pipeline(route()) == []


def test_build_pipeline_orders_rate_limit_before_strip_prefix():
    chain = build_pipeline(route(rate_limit=config(), strip=True))
    assert [type(m) for m in chain] == [RateLimit, StripPrefix]  # reject before work


def test_server_rate_limits_after_exceeding(mock_upstream):
    cfg = GatewayConfig(
        port=0,
        global_timeout="30s",
        routes=[
            RouteConfig(
                path="/svc",
                methods=["GET"],
                strip_prefix=True,
                upstream=UpstreamConfig(url=mock_upstream.base_url),
                rate_limit=config(requests=2),
            )
        ],
    )
    with GatewayServer(cfg) as server:
        statuses, retry_after = [], None
        for _ in range(3):
            conn = http.client.HTTPConnection("127.0.0.1", server.port)
            conn.request("GET", "/svc/echo")
            resp = conn.getresponse()
            resp.read()
            statuses.append(resp.status)
            if resp.status == 429:
                retry_after = resp.getheader("Retry-After")
            conn.close()
    assert statuses == [200, 200, 429]
    assert retry_after == "60"

"""Middleware base and the pipeline runner.

A feature = a Middleware subclass. Each route compiles its config into an
ordered list of middleware; run_pipeline threads a RequestContext through them
(outer->in), with `terminal` (the upstream call) as the core. Middleware may
short-circuit by returning a Response without calling next, and may post-process
the Response on the way back out (inner->out).
"""

import json
import time
from typing import Callable

from gatewaykit.config import RateLimit as RateLimitConfig
from gatewaykit.config import RouteConfig
from gatewaykit.core import RequestContext, Response
from gatewaykit.ratelimit import FixedWindowLimiter, SlidingWindowLimiter


class Middleware:
    def handle(self, ctx: RequestContext, next: Callable[[RequestContext], Response]) -> Response:
        return next(ctx)  # default: pass through


_LIMITERS = {"fixed_window": FixedWindowLimiter, "sliding_window": SlidingWindowLimiter}


class RateLimit(Middleware):
    """Reject requests over the configured rate with 429 + Retry-After.

    Buckets per client IP or globally; the strategy (fixed/sliding window) and
    limits come from config. The limiter is built once (in build_pipeline) so its
    state persists across requests.
    """

    def __init__(self, config: RateLimitConfig, clock: Callable[[], float] = time.monotonic):
        self._limiter = _LIMITERS[config.strategy](config.requests, config.window, clock)
        self._per = config.per

    def handle(self, ctx, next):
        key = ctx.client_ip if self._per == "ip" else "global"
        decision = self._limiter.check(key)
        if not decision.allowed:
            return _too_many_requests(decision.retry_after)
        return next(ctx)


def _too_many_requests(retry_after: int) -> Response:
    body = json.dumps({"error": "rate_limited", "retry_after": retry_after}).encode()
    headers = {"Content-Type": "application/json", "Retry-After": str(retry_after)}
    return Response(429, headers, body)


class StripPrefix(Middleware):
    """Remove the matched route prefix from the forwarded path.

    e.g. route /api/products + request /api/products/123 -> upstream sees /123.
    """

    def handle(self, ctx, next):
        remainder = ctx.upstream_path[len(ctx.route.path):]
        if not remainder.startswith("/"):
            remainder = "/" + remainder  # exact match -> "/"; "?q" -> "/?q"
        ctx.upstream_path = remainder
        return next(ctx)


def build_pipeline(
    route: RouteConfig, global_rate_limit: RateLimitConfig | None = None
) -> list[Middleware]:
    """Compile a route's config into its ordered middleware chain.

    Built once at startup so stateful middleware (e.g. rate limiters) keep their
    state across requests. New features append here.
    """
    chain: list[Middleware] = []
    # Route-level rate_limit overrides the gateway-wide global_rate_limit default.
    rate_limit = route.rate_limit or global_rate_limit
    if rate_limit:
        chain.append(RateLimit(rate_limit))  # outermost: reject before any work
    if route.strip_prefix:
        chain.append(StripPrefix())
    return chain


def run_pipeline(
    ctx: RequestContext,
    middleware: list[Middleware],
    terminal: Callable[[RequestContext], Response],
) -> Response:
    """Thread ctx through the middleware chain, with terminal as the innermost call."""

    def make_next(index: int) -> Callable[[RequestContext], Response]:
        if index == len(middleware):
            return terminal
        return lambda ctx: middleware[index].handle(ctx, make_next(index + 1))

    return make_next(0)(ctx)

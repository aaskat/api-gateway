"""Middleware base and the pipeline runner.

A feature = a Middleware subclass. Each route compiles its config into an
ordered list of middleware; run_pipeline threads a RequestContext through them
(outer->in), with `terminal` (the upstream call) as the core. Middleware may
short-circuit by returning a Response without calling next, and may post-process
the Response on the way back out (inner->out).
"""

from typing import Callable

from gatewaykit.config import RouteConfig
from gatewaykit.core import RequestContext, Response


class Middleware:
    def handle(self, ctx: RequestContext, next: Callable[[RequestContext], Response]) -> Response:
        return next(ctx)  # default: pass through


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


def build_pipeline(route: RouteConfig) -> list[Middleware]:
    """Compile a route's config into its ordered middleware chain.

    Built once at startup so stateful middleware (e.g. rate limiters) keep their
    state across requests. New features append here.
    """
    chain: list[Middleware] = []
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

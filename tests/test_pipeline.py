"""Tier 1(skeleton): the middleware pipeline contract.

Pure tests with fake middleware — no HTTP, no upstream.
"""

from gatewaykit.core import RequestContext, Response
from gatewaykit.middleware import Middleware, run_pipeline


def make_ctx() -> RequestContext:
    return RequestContext("GET", "/p", {}, b"", "1.2.3.4", route=None, upstream_path="/p")


def fresh_terminal(ctx) -> Response:
    return Response(200, {}, b"terminal")


def test_empty_pipeline_calls_terminal():
    resp = run_pipeline(make_ctx(), [], fresh_terminal)
    assert resp.body == b"terminal"


def test_passthrough_middleware_reaches_terminal():
    resp = run_pipeline(make_ctx(), [Middleware()], fresh_terminal)
    assert resp.body == b"terminal"


def test_middleware_can_short_circuit():
    calls = []

    class ShortCircuit(Middleware):
        def handle(self, ctx, next):
            return Response(401, {}, b"blocked")

    def terminal_spy(ctx):
        calls.append(1)
        return fresh_terminal(ctx)

    resp = run_pipeline(make_ctx(), [ShortCircuit()], terminal_spy)
    assert resp.status == 401
    assert calls == []  # terminal never reached


def test_middleware_runs_in_order():
    order = []

    class Tag(Middleware):
        def __init__(self, name):
            self.name = name

        def handle(self, ctx, next):
            order.append(self.name)
            return next(ctx)

    run_pipeline(make_ctx(), [Tag("a"), Tag("b")], fresh_terminal)
    assert order == ["a", "b"]


def test_response_post_processing_runs_in_reverse():
    class Mark(Middleware):
        def __init__(self, name):
            self.name = name

        def handle(self, ctx, next):
            resp = next(ctx)
            resp.headers["X-Order"] = resp.headers.get("X-Order", "") + self.name
            return resp

    resp = run_pipeline(make_ctx(), [Mark("a"), Mark("b")], fresh_terminal)
    assert resp.headers["X-Order"] == "ba"  # inner (b) marks first on the way out

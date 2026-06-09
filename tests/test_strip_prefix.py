"""Tier 1: strip_prefix middleware + pipeline build + server integration."""

import http.client
import json

from gatewaykit.config import GatewayConfig, RouteConfig, UpstreamConfig
from gatewaykit.core import RequestContext, Response
from gatewaykit.middleware import StripPrefix, build_pipeline
from gatewaykit.server import GatewayServer


def route(path: str, strip: bool) -> RouteConfig:
    return RouteConfig(
        path=path, methods=["GET"], strip_prefix=strip, upstream=UpstreamConfig(url="http://x")
    )


def stripped(path: str, route_path: str) -> str:
    r = route(route_path, True)
    ctx = RequestContext("GET", path, {}, b"", "1.1.1.1", route=r, upstream_path=path)
    StripPrefix().handle(ctx, lambda c: Response(200, {}, b""))
    return ctx.upstream_path


def test_strip_prefix_removes_route_prefix():
    assert stripped("/api/products/123", "/api/products") == "/123"


def test_strip_prefix_exact_path_becomes_root():
    assert stripped("/api/products", "/api/products") == "/"


def test_strip_prefix_preserves_query():
    assert stripped("/api/products/1?x=2", "/api/products") == "/1?x=2"


def test_build_pipeline_includes_strip_when_true():
    chain = build_pipeline(route("/svc", True))
    assert len(chain) == 1 and isinstance(chain[0], StripPrefix)


def test_build_pipeline_empty_when_false():
    assert build_pipeline(route("/svc", False)) == []


def test_server_strips_prefix_before_forwarding(mock_upstream):
    config = GatewayConfig(
        port=0,
        global_timeout="30s",
        routes=[
            RouteConfig(
                path="/svc",
                methods=["GET"],
                strip_prefix=True,
                upstream=UpstreamConfig(url=mock_upstream.base_url),
            )
        ],
    )
    with GatewayServer(config) as server:
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("GET", "/svc/echo")
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        assert resp.status == 200
        assert json.loads(data)["path"] == "/echo"

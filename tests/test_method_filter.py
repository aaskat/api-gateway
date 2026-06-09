"""Tier 0(f): method filtering (405) and 404 for unmatched paths, over HTTP."""

import http.client

from gatewaykit.config import GatewayConfig, RouteConfig, UpstreamConfig
from gatewaykit.server import GatewayServer


def route(path: str, methods: list[str]) -> RouteConfig:
    return RouteConfig(path=path, methods=methods, upstream=UpstreamConfig(url="http://x"))


def make_config(routes: list[RouteConfig]) -> GatewayConfig:
    return GatewayConfig(port=0, global_timeout="30s", routes=routes)


def request(server, method, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.port)
    conn.request(method, path)
    resp = conn.getresponse()
    data = resp.read()
    headers = {k: v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, headers, data


def test_post_to_get_only_route_returns_405():
    with GatewayServer(make_config([route("/api/things", ["GET"])])) as server:
        status, _, _ = request(server, "POST", "/api/things")
        assert status == 405


def test_405_includes_allow_header():
    with GatewayServer(make_config([route("/api/things", ["GET", "PUT"])])) as server:
        status, headers, _ = request(server, "POST", "/api/things")
        assert status == 405
        assert "GET" in headers.get("Allow", "")


def test_allowed_method_passes_filter():
    with GatewayServer(make_config([route("/api/things", ["GET"])])) as server:
        status, _, _ = request(server, "GET", "/api/things")
        assert status not in (404, 405)


def test_unmatched_path_returns_404():
    with GatewayServer(make_config([route("/api/things", ["GET"])])) as server:
        status, _, _ = request(server, "GET", "/nope")
        assert status == 404

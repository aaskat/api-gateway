"""Tier 0(g): forward to upstream + hop-by-hop header handling."""

import http.client
import json

from gatewaykit.config import GatewayConfig, RouteConfig, UpstreamConfig
from gatewaykit.proxy import forward, strip_hop_by_hop
from gatewaykit.server import GatewayServer


def test_strip_hop_by_hop_removes_them():
    headers = {"Connection": "keep-alive", "Keep-Alive": "timeout=5", "X-Keep": "yes"}
    result = strip_hop_by_hop(headers)
    assert "X-Keep" in result
    lowered = {k.lower() for k in result}
    assert "connection" not in lowered
    assert "keep-alive" not in lowered


def test_forward_get_returns_upstream_response(mock_upstream):
    resp = forward("GET", mock_upstream.base_url, "/echo", {}, b"", 5.0)
    assert resp.status == 200
    payload = json.loads(resp.body)
    assert payload["method"] == "GET"
    assert payload["path"] == "/echo"


def test_forward_post_sends_body(mock_upstream):
    resp = forward("POST", mock_upstream.base_url, "/echo", {}, b'{"a":1}', 5.0)
    assert json.loads(resp.body)["body"] == '{"a":1}'


def test_forward_passes_custom_header(mock_upstream):
    resp = forward("GET", mock_upstream.base_url, "/echo", {"X-Test": "abc"}, b"", 5.0)
    assert json.loads(resp.body)["headers"]["X-Test"] == "abc"


def test_forward_upstream_down_returns_502():
    resp = forward("GET", "http://127.0.0.1:1", "/x", {}, b"", 1.0)
    assert resp.status == 502


def test_server_forwards_to_upstream(mock_upstream):
    config = GatewayConfig(
        port=0,
        global_timeout="30s",
        routes=[
            RouteConfig(
                path="/echo",
                methods=["GET"],
                upstream=UpstreamConfig(url=mock_upstream.base_url),
            )
        ],
    )
    with GatewayServer(config) as server:
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("GET", "/echo")
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        assert resp.status == 200
        assert json.loads(data)["path"] == "/echo"

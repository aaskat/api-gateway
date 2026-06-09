"""Tier 0(d): gateway HTTP server boots on the configured port and serves /health."""

import http.client
import json

from gatewaykit.config import GatewayConfig
from gatewaykit.server import GatewayServer


def make_config(port: int = 0) -> GatewayConfig:
    """Minimal valid config; port 0 = ephemeral so tests never clobber 8080."""
    return GatewayConfig(port=port, global_timeout="30s", routes=[])


def get(server, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.port)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_health_over_http_returns_200_and_payload():
    with GatewayServer(make_config()) as server:
        status, data = get(server, "/health")
        assert status == 200
        body = json.loads(data)
        assert body["status"] == "healthy"
        assert isinstance(body["uptime_seconds"], int)


def test_server_binds_a_port():
    with GatewayServer(make_config()) as server:
        assert server.port > 0


def test_unknown_path_returns_404():
    with GatewayServer(make_config()) as server:
        status, _ = get(server, "/nope")
        assert status == 404

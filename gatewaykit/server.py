"""The gateway HTTP server: ThreadingHTTPServer bound to the configured port.

For now it serves GET /health (bypassing the pipeline) and returns 404 for
everything else. The router, method filter, and proxy replace the 404 fallback
in later units.
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Callable
from urllib.parse import urlsplit

from gatewaykit.config import GatewayConfig
from gatewaykit.core import Response
from gatewaykit.health import HealthCheck
from gatewaykit.router import Router


class _Handler(BaseHTTPRequestHandler):
    def _dispatch(self):
        path = urlsplit(self.path).path
        if self.command == "GET" and path == "/health":
            self._send(self.server.health.response())
            return

        route = self.server.router.match(path)
        if route is None:
            self._send(_not_found(path))
        elif self.command not in route.methods:
            self._send(_method_not_allowed(route.methods))
        else:
            self._send(_not_implemented())  # placeholder until the proxy lands (0g)

    do_GET = _dispatch
    do_POST = _dispatch
    do_PUT = _dispatch
    do_DELETE = _dispatch
    do_PATCH = _dispatch

    def _send(self, resp: Response):
        self.send_response(resp.status)
        for key, value in resp.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(resp.body)))
        self.end_headers()
        self.wfile.write(resp.body)

    def log_message(self, *args):
        pass


def _not_found(path: str) -> Response:
    body = json.dumps({"error": "not_found", "path": path}).encode()
    return Response(404, {"Content-Type": "application/json"}, body)


def _method_not_allowed(allowed: list[str]) -> Response:
    body = json.dumps({"error": "method_not_allowed", "allowed": allowed}).encode()
    # RFC 7231: a 405 response must list permitted methods in Allow.
    headers = {"Content-Type": "application/json", "Allow": ", ".join(allowed)}
    return Response(405, headers, body)


def _not_implemented() -> Response:
    body = json.dumps({"error": "not_implemented"}).encode()
    return Response(501, {"Content-Type": "application/json"}, body)


class GatewayServer:
    """Threaded gateway server; context manager exposing the bound port."""

    def __init__(self, config: GatewayConfig, clock: Callable[[], float] = time.monotonic):
        self._config = config
        self._server = ThreadingHTTPServer(("127.0.0.1", config.port), _Handler)
        self._server.health = HealthCheck(clock=clock)
        self._server.router = Router(config.routes)
        self.port = self._server.server_address[1]
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "GatewayServer":
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()

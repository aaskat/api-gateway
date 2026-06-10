"""The gateway HTTP server: ThreadingHTTPServer bound to the configured port.

Serves GET /health (bypassing the pipeline). For matched routes it builds a
RequestContext, runs the route's compiled middleware chain, and forwards to the
upstream as the pipeline terminal.
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Callable
from urllib.parse import urlsplit

from gatewaykit.config import GatewayConfig
from gatewaykit.core import RequestContext, Response
from gatewaykit.health import HealthCheck
from gatewaykit.middleware import build_pipeline, run_pipeline
from gatewaykit.proxy import forward
from gatewaykit.router import Router


class _Handler(BaseHTTPRequestHandler):
    def _dispatch(self):
        path = urlsplit(self.path).path
        if self.command == "GET" and path == "/health":
            self._send(self.server.health.response())
            return
        match self.server.router.match(path):
            case None:
                self._send(_not_found(path))
            case route if self.command not in route.methods:
                self._send(_method_not_allowed(route.methods))
            case route:
                self._send(self._handle_route(route))

    def _handle_route(self, route) -> Response:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        ctx = RequestContext(
            method=self.command,
            path=self.path,
            headers=dict(self.headers),
            body=body,
            client_ip=self.client_address[0],
            route=route,
            upstream_path=self.path,  # mutated by strip_prefix and friends
        )
        chain = self.server.chains[id(route)]
        return run_pipeline(ctx, chain, self._forward)

    def _forward(self, ctx: RequestContext) -> Response:
        # Temp: pick targets[0] until load balancing across targets is implemented.
        url = ctx.route.upstream.url if ctx.route.upstream.url else ctx.route.upstream.targets[0].url
        return forward(
            ctx.method,
            url,
            ctx.upstream_path,
            ctx.headers,
            ctx.body,
            self.server.config.global_timeout,
        )

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


class GatewayServer:
    """Threaded gateway server; context manager exposing the bound port."""

    def __init__(self, config: GatewayConfig, clock: Callable[[], float] = time.monotonic):
        self._config = config
        self._server = ThreadingHTTPServer(("127.0.0.1", config.port), _Handler)
        self._server.health = HealthCheck(clock=clock)
        self._server.router = Router(config.routes)
        self._server.config = config
        # Compile each route's middleware chain once, so stateful middleware
        # (rate limiters, circuit breakers) persist across requests.
        self._server.chains = {id(route): build_pipeline(route) for route in config.routes}
        self.port = self._server.server_address[1]
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "GatewayServer":
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()

    def serve_forever(self) -> None:
        """Run in the foreground (used by the CLI entrypoint) until interrupted."""
        print(f"GatewayKit listening on http://127.0.0.1:{self.port}", flush=True)
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._server.server_close()

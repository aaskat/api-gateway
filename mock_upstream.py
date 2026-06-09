"""Mock upstream server for tests (and runnable standalone).

Provides canned endpoints the proxy tests forward to:
  /echo   -> 200, JSON reflecting the received request
  /slow   -> sleeps ?ms=N then 200 (gateway timeout tests)
  /flaky  -> first ?fail=N requests return ?status, then 200 (retry/CB tests)

Run standalone:  python mock_upstream.py [port]
"""

import json
import sys
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import parse_qs, urlsplit


class _Handler(BaseHTTPRequestHandler):
    def _route(self):
        parts = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        with self.server.lock:
            self.server.request_count += 1
        if parts.path == "/echo":
            self._echo(parts.path)
        elif parts.path == "/slow":
            time.sleep(int(query.get("ms", 0)) / 1000.0)
            self._json(200, {"delay_ms": int(query.get("ms", 0))})
        elif parts.path == "/flaky":
            self._flaky(parts.path, query)
        else:
            self._json(404, {"error": "not_found", "path": parts.path})

    do_GET = _route
    do_POST = _route
    do_PUT = _route
    do_DELETE = _route
    do_PATCH = _route

    def _echo(self, path):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else ""
        self._json(
            200,
            {
                "method": self.command,
                "path": path,
                "headers": dict(self.headers),
                "body": body,
            },
        )

    def _flaky(self, path, query):
        fail = int(query.get("fail", 0))
        status = int(query.get("status", 503))
        with self.server.lock:
            seen = self.server.flaky_hits[path]
            self.server.flaky_hits[path] += 1
        if seen < fail:
            self._json(status, {"error": "flaky", "attempt": seen + 1})
        else:
            self._json(200, {"ok": True, "attempt": seen + 1})

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # silence per-request logging in tests


class _Server(ThreadingHTTPServer):
    """ThreadingHTTPServer with shared, lock-guarded counters for flaky/count."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = Lock()
        self.request_count = 0
        self.flaky_hits = defaultdict(int)


class MockUpstream:
    """Threaded mock upstream on an ephemeral port; usable as a context manager."""

    def __init__(self):
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self.host, self.port = self._server.server_address[0], self._server.server_address[1]
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def request_count(self) -> int:
        with self._server.lock:
            return self._server.request_count

    def __enter__(self) -> "MockUpstream":
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    server = _Server(("127.0.0.1", port), _Handler)
    print(f"mock upstream on http://127.0.0.1:{server.server_address[1]}")
    server.serve_forever()

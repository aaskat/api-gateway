"""Upstream forwarding: the core of the request pipeline."""

import http.client
from urllib.parse import urlsplit

from gatewaykit.core import Response

# RFC 2616 sec 13.5.1 - connection-specific headers that must not be proxied.
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)


def strip_hop_by_hop(headers: dict) -> dict:
    """Drop connection-specific headers (case-insensitive); keep end-to-end ones."""
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


def forward(method, upstream_url, path, headers, body, timeout) -> Response:
    """Forward a request to the upstream and return its response.

    Hop-by-hop and Host headers are stripped from the request (http.client sets
    the correct Host); hop-by-hop headers are stripped from the response. Any
    connection failure or timeout becomes a 502 so a dead upstream never crashes
    the worker thread.
    """
    target = urlsplit(upstream_url)
    out_headers = {
        k: v for k, v in strip_hop_by_hop(headers).items() if k.lower() != "host"
    }
    conn = http.client.HTTPConnection(target.hostname, target.port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=out_headers)
        upstream = conn.getresponse()
        resp_body = upstream.read()
        resp_headers = strip_hop_by_hop(dict(upstream.getheaders()))
        return Response(upstream.status, resp_headers, resp_body)
    except (OSError, http.client.HTTPException):
        return Response(
            502,
            {"Content-Type": "application/json"},
            b'{"error": "bad_gateway"}',
        )
    finally:
        conn.close()

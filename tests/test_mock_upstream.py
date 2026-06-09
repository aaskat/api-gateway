"""Tier 0(c): the mock upstream fixture's own contract.

These pin the behavior the proxy tests will rely on. Hit over real HTTP with
the stdlib client (no third-party HTTP libs).
"""

import http.client
import json


def _request(upstream, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(upstream.host, upstream.port)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_echo_reflects_request(mock_upstream):
    status, data = _request(
        mock_upstream,
        "POST",
        "/echo",
        body=b'{"x":1}',
        headers={"X-Test": "abc"},
    )
    assert status == 200
    payload = json.loads(data)
    assert payload["method"] == "POST"
    assert payload["path"] == "/echo"
    assert payload["body"] == '{"x":1}'
    assert payload["headers"]["X-Test"] == "abc"


def test_echo_get(mock_upstream):
    status, data = _request(mock_upstream, "GET", "/echo")
    assert status == 200
    assert json.loads(data)["method"] == "GET"


def test_slow_returns_200_and_echoes_delay(mock_upstream):
    status, data = _request(mock_upstream, "GET", "/slow?ms=20")
    assert status == 200
    assert json.loads(data)["delay_ms"] == 20


def test_flaky_fails_n_times_then_succeeds(mock_upstream):
    path = "/flaky?fail=2&status=503"
    s1, _ = _request(mock_upstream, "GET", path)
    s2, _ = _request(mock_upstream, "GET", path)
    s3, _ = _request(mock_upstream, "GET", path)
    assert (s1, s2, s3) == (503, 503, 200)

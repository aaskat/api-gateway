"""Tier 0(e): longest-prefix, segment-aware routing."""

from gatewaykit.config import RouteConfig, UpstreamConfig
from gatewaykit.router import Router


def route(path: str) -> RouteConfig:
    return RouteConfig(path=path, methods=["GET"], upstream=UpstreamConfig(url="http://x"))


def test_exact_path_match():
    router = Router([route("/api/users")])
    assert router.match("/api/users").path == "/api/users"


def test_subpath_matches_prefix():
    router = Router([route("/api/users")])
    assert router.match("/api/users/123").path == "/api/users"


def test_longest_prefix_wins():
    router = Router([route("/api"), route("/api/users")])
    assert router.match("/api/users/1").path == "/api/users"


def test_segment_boundary_no_false_match():
    router = Router([route("/api/users")])
    assert router.match("/api/usersfoo") is None


def test_no_match_returns_none():
    router = Router([route("/api/users")])
    assert router.match("/nope") is None

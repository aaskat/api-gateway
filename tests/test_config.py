"""Tier 0(a): config loader, duration parsing, fail-fast validation.

The tests ARE the spec. They derive from gateway.yaml semantics and the Core
Requirements. Failure modes are pinned with their own tests; ConfigError is the
single assertion target for every invalid-config case.
"""

import textwrap

import pytest

from gatewaykit.config import ConfigError, load_config, parse_duration


# A complete, valid config matching the provided gateway.yaml schema. Inlined so
# the unit tests are self-contained and deterministic (no reliance on a repo file).
VALID_CONFIG = textwrap.dedent(
    """
    gateway:
      port: 8080
      global_timeout: "30s"
      global_rate_limit:
        requests: 100
        window: "60s"
        strategy: "fixed_window"
        per: "ip"
    routes:
      - path: "/api/users"
        methods: ["GET", "POST"]
        strip_prefix: false
        upstream:
          url: "http://localhost:3001"
        rate_limit:
          requests: 30
          window: "60s"
          strategy: "sliding_window"
          per: "ip"
      - path: "/api/orders"
        methods: ["GET", "POST", "PUT"]
        strip_prefix: false
        upstream:
          url: "http://localhost:3002"
          timeout: "5s"
        retry:
          attempts: 3
          backoff: "exponential"
          initial_delay: "1s"
          on: [502, 503, 504]
      - path: "/api/products"
        methods: ["GET"]
        strip_prefix: true
        upstream:
          targets:
            - url: "http://localhost:3003"
              weight: 3
            - url: "http://localhost:3004"
              weight: 1
          balance: "weighted_round_robin"
          timeout: "10s"
      - path: "/api/legacy"
        methods: ["GET", "POST"]
        strip_prefix: true
        upstream:
          url: "http://localhost:3005"
      - path: "/api/internal"
        methods: ["GET", "POST"]
        strip_prefix: false
        upstream:
          url: "http://localhost:3006"
        auth:
          type: "api_key"
          header: "X-API-Key"
          keys: ["sk_live_abc123", "sk_live_def456"]
      - path: "/api/catchall"
        methods: ["GET"]
        strip_prefix: false
        upstream:
          url: "http://localhost:3007"
    """
)


def write_config(tmp_path, content: str) -> str:
    """Write `content` to a temp file and return its path as a string."""
    p = tmp_path / "gateway.yaml"
    p.write_text(content)
    return str(p)


def route_by_path(config, path: str):
    """Look routes up by path so tests don't couple to ordering."""
    return next(r for r in config.routes if r.path == path)


# --------------------------------------------------------------------------- #
# parse_duration
# --------------------------------------------------------------------------- #


def test_parse_duration_seconds():
    assert parse_duration("30s") == 30.0


def test_parse_duration_subsecond_ms():
    assert parse_duration("500ms") == 0.5


def test_parse_duration_minutes():
    assert parse_duration("5m") == 300.0


def test_parse_duration_hours():
    assert parse_duration("2h") == 7200.0


def test_parse_duration_missing_unit_raises():
    with pytest.raises(ConfigError):
        parse_duration("30")


def test_parse_duration_garbage_raises():
    with pytest.raises(ConfigError):
        parse_duration("abc")
    with pytest.raises(ConfigError):
        parse_duration("")


def test_parse_duration_negative_raises():
    with pytest.raises(ConfigError):
        parse_duration("-5s")


# --------------------------------------------------------------------------- #
# load_config — valid config
# --------------------------------------------------------------------------- #


def test_load_valid_config_parses_gateway_block(tmp_path):
    config = load_config(write_config(tmp_path, VALID_CONFIG))
    assert config.port == 8080
    assert config.global_timeout == 30.0
    assert config.global_rate_limit.requests == 100
    assert config.global_rate_limit.window == 60.0
    assert config.global_rate_limit.strategy == "fixed_window"
    assert config.global_rate_limit.per == "ip"


def test_load_parses_all_routes(tmp_path):
    config = load_config(write_config(tmp_path, VALID_CONFIG))
    assert len(config.routes) == 6
    users = route_by_path(config, "/api/users")
    assert users.methods == ["GET", "POST"]
    assert users.strip_prefix is False
    assert users.upstream.url == "http://localhost:3001"


def test_load_route_timeout_override(tmp_path):
    config = load_config(write_config(tmp_path, VALID_CONFIG))
    orders = route_by_path(config, "/api/orders")
    assert orders.upstream.timeout == 5.0


def test_load_weighted_targets(tmp_path):
    config = load_config(write_config(tmp_path, VALID_CONFIG))
    products = route_by_path(config, "/api/products")
    assert products.upstream.balance == "weighted_round_robin"
    assert len(products.upstream.targets) == 2
    assert products.upstream.targets[0].url == "http://localhost:3003"
    assert products.upstream.targets[0].weight == 3


# --------------------------------------------------------------------------- #
# load_config — fail fast
# --------------------------------------------------------------------------- #


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(str(tmp_path / "does_not_exist.yaml"))


def test_malformed_yaml_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, "gateway: : : [unbalanced"))


def test_missing_gateway_port_raises(tmp_path):
    bad = textwrap.dedent(
        """
        gateway:
          global_timeout: "30s"
        routes:
          - path: "/api/users"
            methods: ["GET"]
            upstream:
              url: "http://localhost:3001"
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, bad))


def test_route_missing_path_raises(tmp_path):
    bad = textwrap.dedent(
        """
        gateway:
          port: 8080
          global_timeout: "30s"
        routes:
          - methods: ["GET"]
            upstream:
              url: "http://localhost:3001"
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, bad))


def test_route_missing_upstream_raises(tmp_path):
    bad = textwrap.dedent(
        """
        gateway:
          port: 8080
          global_timeout: "30s"
        routes:
          - path: "/api/users"
            methods: ["GET"]
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, bad))


def test_invalid_rate_limit_strategy_raises(tmp_path):
    bad = textwrap.dedent(
        """
        gateway:
          port: 8080
          global_timeout: "30s"
          global_rate_limit:
            requests: 100
            window: "60s"
            strategy: "bogus_strategy"
            per: "ip"
        routes:
          - path: "/api/users"
            methods: ["GET"]
            upstream:
              url: "http://localhost:3001"
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, bad))


def test_invalid_balance_strategy_raises(tmp_path):
    bad = textwrap.dedent(
        """
        gateway:
          port: 8080
          global_timeout: "30s"
        routes:
          - path: "/api/products"
            methods: ["GET"]
            upstream:
              targets:
                - url: "http://localhost:3003"
                  weight: 1
              balance: "bogus_balance"
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, bad))


def test_upstream_with_neither_url_nor_targets_raises(tmp_path):
    bad = textwrap.dedent(
        """
        gateway:
          port: 8080
          global_timeout: "30s"
        routes:
          - path: "/api/users"
            methods: ["GET"]
            upstream:
              timeout: "5s"
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, bad))


def test_invalid_duration_in_config_raises(tmp_path):
    bad = textwrap.dedent(
        """
        gateway:
          port: 8080
          global_timeout: "30"
        routes:
          - path: "/api/users"
            methods: ["GET"]
            upstream:
              url: "http://localhost:3001"
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, bad))

"""Config loading, validation, and duration parsing for GatewayKit.

The config file IS the spec: this module turns a YAML file into validated,
typed objects and fails fast (raising ConfigError) on anything malformed, so a
broken config is caught at startup rather than on the first request.
"""

import re
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ValidationError, model_validator


class ConfigError(Exception):
    """The single public failure boundary for invalid configuration.

    load_config wraps pydantic's ValidationError, YAML parse errors, and file
    errors in this type so callers never depend on pydantic/yaml internals.
    """


_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h)$")
_DURATION_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration(value: str) -> float:
    """Parse a duration string like "30s" / "500ms" / "5m" / "2h" into seconds.

    Requires an explicit unit: a bare number ("30") is rejected rather than
    guessed, and garbage / negative values raise ConfigError.
    """
    match = _DURATION_RE.match(value) if isinstance(value, str) else None
    if not match:
        raise ConfigError(f"invalid duration: {value!r} (expected e.g. '30s', '500ms')")
    amount, unit = match.groups()
    return float(amount) * _DURATION_UNITS[unit]


# A duration field: accepts the human string, stores seconds as a float.
Duration = Annotated[float, BeforeValidator(parse_duration)]


class RateLimit(BaseModel):
    requests: int
    window: Duration
    strategy: Literal["fixed_window", "sliding_window"]
    per: Literal["ip", "global"]


class Target(BaseModel):
    url: str
    weight: int = 1


class UpstreamConfig(BaseModel):
    url: str | None = None
    targets: list[Target] | None = None
    balance: Literal["round_robin", "weighted_round_robin"] | None = None
    timeout: Duration | None = None

    @model_validator(mode="after")
    def _require_url_or_targets(self) -> "UpstreamConfig":
        if not self.url and not self.targets:
            raise ValueError("upstream must define either 'url' or 'targets'")
        return self


class RouteConfig(BaseModel):
    path: str
    methods: list[str]
    strip_prefix: bool = False
    upstream: UpstreamConfig
    rate_limit: RateLimit | None = None
    # Advanced blocks kept as pass-through until their feature is built, so any
    # valid config loads. Each gets a real sub-model when we TDD that feature.
    retry: dict | None = None
    auth: dict | None = None
    circuit_breaker: dict | None = None
    request_transform: dict | None = None
    response_transform: dict | None = None
    health_check: dict | None = None


class GatewayConfig(BaseModel):
    port: int
    global_timeout: Duration
    global_rate_limit: RateLimit | None = None
    routes: list[RouteConfig]


def load_config(path: str) -> GatewayConfig:
    """Read YAML from `path`, validate, and return a GatewayConfig.

    Flattens the top-level `gateway:` block and `routes:` list into one model.
    Every failure mode (missing file, malformed YAML, schema/duration errors)
    surfaces as ConfigError.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except OSError as e:
        raise ConfigError(f"cannot read config file {path!r}: {e}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"malformed YAML in {path!r}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"config root must be a mapping, got {type(data).__name__}")

    gateway = data.get("gateway") or {}
    merged = {**gateway, "routes": data.get("routes", [])}

    try:
        return GatewayConfig(**merged)
    except ConfigError:
        raise  # a duration validator already produced a clear ConfigError
    except ValidationError as e:
        raise ConfigError(f"invalid config: {e}") from e

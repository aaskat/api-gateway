# GatewayKit

A lightweight, config-driven API gateway built from scratch in Python (standard
library for all HTTP, plus PyYAML for config parsing and Pydantic for
validation). It reads a `gateway.yaml`, routes and proxies requests to upstream
services, and applies per-route policies through a middleware pipeline.

## Prerequisites

- Python 3.13 (uses `match` statements and `X | None` types)
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

Dependencies (`requirements.txt`): `pydantic`, `pydantic-settings`, `pyyaml`,
and `pytest` (tests only).

## Setup

```bash
# with uv (recommended)
uv venv --python 3.13
uv pip install -r requirements.txt

# or with pip
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run the gateway

```bash
# explicit config path...
.venv/bin/python -m gatewaykit gateway.yaml

# ...or let it resolve from env / .env / default ("gateway.yaml")
cp .env.example .env        # GATEWAYKIT_CONFIG=gateway.yaml
.venv/bin/python -m gatewaykit
```

Config path precedence: CLI arg → `GATEWAYKIT_CONFIG` env var → `.env` file →
default `gateway.yaml`. The gateway listens on the `port` from the config (8080
in the example) and always serves `GET /health`. Invalid config fails fast with
a clear message and a non-zero exit code.

```bash
curl localhost:8080/health
# {"status":"healthy","uptime_seconds":3}
```

## Run the tests (single command)

```bash
.venv/bin/python -m pytest
```

Tests are fully self-contained: a threaded mock upstream (`mock_upstream/`) runs
on an ephemeral port as a pytest fixture, and all time-based logic uses an
injected clock so nothing sleeps. Run the mock standalone with
`python -m mock_upstream [port]`.

## Implemented config features

| Feature | Status |
|---|---|
| Load config from YAML (CLI arg / env / `.env`) | ✅ |
| `GET /health` → 200 `{status, uptime_seconds}` | ✅ |
| Duration parsing (`ms`/`s`/`m`/`h`), fail-fast validation | ✅ |
| Routing — longest-prefix, segment-aware | ✅ |
| Method filtering → 405 + `Allow` header | ✅ |
| Proxying + hop-by-hop header stripping | ✅ |
| Upstream down / timeout → 502 | ✅ |
| `strip_prefix` | ✅ |
| Middleware pipeline (one feature = one middleware) | ✅ |
| Rate limiting — `fixed_window` + `sliding_window`, thread-safe | ⚠️ built & tested, **not yet wired into the request path** |
| `auth` (api_key) | ❌ parsed, not enforced |
| Per-route `timeout` override | ❌ parsed; global timeout applied |
| `retry` / backoff | ❌ parsed, not implemented |
| Load balancing (`targets`/`weight`/`balance`) + health checks | ❌ parsed, not implemented |
| `circuit_breaker` | ❌ parsed, not implemented |
| `request_transform` / `response_transform` | ❌ parsed, not implemented |

Unimplemented config blocks are still parsed and preserved (the gateway loads
any valid config), so they're ready for the middleware that will consume them.
See `DECISIONS.md` for priorities and trade-offs.

# Decisions

## Process: strict TDD

- **Every unit was built test-first:** wrote the failing test(s), confirmed a *meaningful* red (a real assertion failure, never an import/syntax error), then the minimal code to go green.
- Committed each red→green cycle separately — the **commit history is the story** of how the gateway grew.
- Time-based logic (rate-limit windows) tested via an injected clock, so tests are deterministic and never `sleep`.
- Result: 69 tests, all green, suite self-contained (mock upstream on an ephemeral port).

## How I prioritized

- Built bottom-up, smallest testable unit first — gateway stays runnable + correct at every step.
- Order: config loader → core path (`/health`/router/method filter/proxy) → middleware pipeline + `strip_prefix` → rate limiting.
- Core path first = all 5 non-negotiable requirements covered early.
- Rate limiting next = the explicit Production-Thinking exhibit ("50 concurrent requests").
- Trade-off: few features built cleanly + tested > many half-working.

## Architecture & trade-offs

- **Middleware pipeline:** each route compiles config → ordered `Middleware` list once at startup; `run_pipeline` threads a `RequestContext` through them, upstream `forward` is the terminal.
- **Add a feature = one `Middleware` subclass + one line in `build_pipeline`.**
- Middleware can short-circuit (return `Response`, skip `next`) or post-process on the way out.
- Chains compiled once → stateful middleware (rate limiter) keep state across requests.
- **Config-driven + typed:** Pydantic models; `Literal` enums validate free; one `parse_duration` via `BeforeValidator`.
- **Single failure boundary:** `load_config` wraps file/YAML/schema errors as `ConfigError` — callers never touch Pydantic internals.
- **Stdlib proxy:** `http.server`/`http.client`, `ThreadingHTTPServer` (thread per request); shared counters lock-guarded.
- **Dependency exception:** Pydantic + pydantic-settings used as *validation*, not an HTTP/proxy framework — deliberate, documented.
- **Testable by design:** injected `clock` (advance fake time, never `sleep`); mock upstream on ephemeral port → self-contained suite.

## Production thinking

- Upstream down/timeout → `502` (caught in `forward`, worker thread survives).
- Malformed config → fail-fast `ConfigError` + non-zero exit; never boots half-configured.
- Concurrency → evict/count/admit under one lock; 50-thread test asserts exactly the limit, no overcount.
- Hop-by-hop headers stripped both directions (RFC 2616 §13.5.1).

## Partially implemented

- **Rate limiting:** both `FixedWindowLimiter` + `SlidingWindowLimiter` done, thread-safe, fully tested (incl. concurrency).
- The `RateLimit` *middleware* (strategy select, ip/global bucket, `429 + Retry-After`) is **not yet wired into `build_pipeline`** → not active on live requests. Remaining: middleware class + 1 line.
- `auth` / `retry` / `targets` (LB) / `circuit_breaker` / transforms / per-route `timeout`: **parsed + preserved, not enforced** (any valid config still loads).

## What I'd build next (in order)

1. Wire `RateLimit` middleware into the pipeline (`429 + Retry-After`, route-overrides-global).
2. `api_key` auth middleware (short-circuit 401).
3. Per-route `timeout` override (already parsed; thread to `forward`).
4. `retry` with fixed/exponential backoff.
5. Load balancing (`targets`, round-robin/weighted) + health checks.
6. `circuit_breaker`, then request/response transforms.
7. Token-bucket limiter strategy.

## How I used AI tools

- Claude Code under strict TDD I drove as lead: propose behavior + test cases → approve → write tests → confirm meaningful red → minimal code to green → commit each cycle.
- Commit history reflects that red→green loop.
- I made the architecture + ambiguity calls (reject unitless durations, segment-aware routing, sliding-vs-fixed, Pydantic exception, `.env` settings); assistant drafted code/tests against them.

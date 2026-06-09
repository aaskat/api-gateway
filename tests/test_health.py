"""Tier 0(b): GET /health responder. Deterministic via an injected clock."""

import json

from gatewaykit.health import HealthCheck


class FakeClock:
    """Controllable monotonic clock: tests advance time instead of sleeping."""

    def __init__(self, now: float = 0.0):
        self._now = now

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_health_returns_200():
    health = HealthCheck(clock=FakeClock())
    assert health.response().status == 200


def test_health_status_is_healthy():
    health = HealthCheck(clock=FakeClock())
    body = json.loads(health.response().body)
    assert body["status"] == "healthy"


def test_health_content_type_is_json():
    health = HealthCheck(clock=FakeClock())
    assert health.response().headers["Content-Type"] == "application/json"


def test_uptime_is_zero_at_start():
    health = HealthCheck(clock=FakeClock())
    body = json.loads(health.response().body)
    assert body["uptime_seconds"] == 0


def test_uptime_tracks_clock():
    clock = FakeClock()
    health = HealthCheck(clock=clock)
    clock.advance(5)
    body = json.loads(health.response().body)
    assert body["uptime_seconds"] == 5


def test_uptime_truncated_to_int():
    clock = FakeClock()
    health = HealthCheck(clock=clock)
    clock.advance(2.9)
    body = json.loads(health.response().body)
    assert body["uptime_seconds"] == 2

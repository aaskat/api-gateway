"""The /health responder: always-healthy status with uptime."""

import time
from typing import Callable

from pydantic import BaseModel

from gatewaykit.core import Response


class HealthStatus(BaseModel):
    """Typed response contract for GET /health."""

    status: str
    uptime_seconds: int


class HealthCheck:
    """Produces the GET /health response, config-independent.

    Clock is injected so tests advance time deterministically (no sleep).
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._start = clock()

    def response(self) -> Response:
        return Response(
            status=200,
            headers={"Content-Type": "application/json"},
            body=HealthStatus(
                status="healthy", 
                uptime_seconds=int(self._clock() - self._start)
                ).model_dump_json().encode(),
        )

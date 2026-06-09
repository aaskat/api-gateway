"""Shared pipeline currency: RequestContext (inbound) and Response (outbound)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatewaykit.config import RouteConfig


@dataclass
class Response:
    """Gateway's internal representation of an HTTP response."""

    status: int
    headers: dict[str, str]
    body: bytes


@dataclass
class RequestContext:
    """Carries one request through the middleware pipeline.

    `path` is the original request target (incl. query); `upstream_path` is what
    gets forwarded and starts equal to it — strip_prefix and friends mutate it.
    """

    method: str
    path: str
    headers: dict[str, str]
    body: bytes
    client_ip: str
    route: "RouteConfig"
    upstream_path: str

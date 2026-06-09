"""Shared pipeline currency: the internal Response (and later RequestContext)."""

from dataclasses import dataclass


@dataclass
class Response:
    """Gateway's internal representation of an HTTP response."""

    status: int
    headers: dict[str, str]
    body: bytes

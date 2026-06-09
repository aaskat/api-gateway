"""Shared test fixtures."""

import pytest

from mock_upstream import MockUpstream


@pytest.fixture
def mock_upstream():
    """A fresh threaded mock upstream per test (resets flaky counters)."""
    with MockUpstream() as upstream:
        yield upstream

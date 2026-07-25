"""pytest configuration for the benchmark suite.

All benchmarks require a running Priveil API.  Set PRIVEIL_API_URL to override
the default; the entire session is skipped if the API is unreachable.

    PRIVEIL_API_URL=http://localhost:8000 make bench
"""

from __future__ import annotations

import os

import httpx
import pytest


def _api_url() -> str:
    return os.environ.get("PRIVEIL_API_URL", "http://localhost:8000").rstrip("/")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "benchmark: marks benchmark tests (run with --benchmark-only)"
    )


@pytest.fixture(scope="session")
def api_url() -> str:
    return _api_url()


@pytest.fixture(scope="session", autouse=True)
def require_api(api_url: str) -> None:
    """Skip the entire session if the API is not reachable."""
    try:
        resp = httpx.get(f"{api_url}/health", timeout=3.0)
        resp.raise_for_status()
    except Exception as exc:
        pytest.skip(
            f"Priveil API not reachable at {api_url} ({exc}). "
            "Start it with 'make serve' then re-run 'make bench'."
        )


@pytest.fixture(scope="session")
def client(api_url: str) -> httpx.Client:
    """Shared sync httpx client — connection-pooled across all benchmarks."""
    with httpx.Client(base_url=api_url, timeout=30.0) as c:
        yield c

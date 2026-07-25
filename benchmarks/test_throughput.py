"""API throughput benchmarks for Priveil.

Requires a running API (see benchmarks/conftest.py).  Run with::

    make bench                          # saves benchmarks/results.json
    make bench PRIVEIL_API_URL=http://host:8000

Each scenario in benchmarks/data/*.json is benchmarked independently.
Scenarios declare the expected entity types, which are verified before
timing begins so a misconfigured server doesn't silently skew results.

Comparing runs::

    git diff benchmarks/results.json    # see what changed after a code change
    make bench                          # overwrite with fresh measurements
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

import httpx
import pytest

# ── scenario loader ────────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).parent / "data"


def _load_scenarios() -> list[dict]:
    scenarios = []
    for path in sorted(_DATA_DIR.glob("*.json")):
        scenarios.append(json.loads(path.read_text()))
    return scenarios


_SCENARIOS = _load_scenarios()
_SCENARIO_IDS = [s["name"] for s in _SCENARIOS]


# ── correctness gate ───────────────────────────────────────────────────────────


class TestScenarioCorrectness:
    """Verify each scenario returns its declared entity types before benchmarking.

    These run in normal (non-benchmark) mode too — they serve as smoke tests
    that the API is actually detecting what the scenario says it should.
    Timing is irrelevant here; if these fail the bench numbers are meaningless.
    """

    @pytest.mark.parametrize("scenario", _SCENARIOS, ids=_SCENARIO_IDS)
    def test_expected_entities_detected(self, client: httpx.Client, scenario: dict) -> None:
        resp = client.post("/detect", json={"text": scenario["text"], "mode": scenario["mode"]})
        assert resp.status_code == 200, f"Non-200 from API: {resp.text}"
        found = {e["entity_type"] for e in resp.json()["data"]["entities"]}
        for expected_type in scenario["expected_entity_types"]:
            assert expected_type in found, (
                f"Scenario '{scenario['name']}': expected {expected_type} but got {found}"
            )

    @pytest.mark.parametrize("scenario", _SCENARIOS, ids=_SCENARIO_IDS)
    def test_response_envelope_shape(self, client: httpx.Client, scenario: dict) -> None:
        resp = client.post("/detect", json={"text": scenario["text"], "mode": scenario["mode"]})
        body = resp.json()
        assert "meta" in body
        assert "data" in body
        assert "entities" in body["data"]
        assert body["meta"]["response"]["input_hash"].startswith("hmac-sha256:")


# ── per-scenario latency benchmarks ───────────────────────────────────────────


class TestScenarioThroughput:
    """One benchmark per scenario — measures median latency of a single POST /detect."""

    @pytest.mark.parametrize("scenario", _SCENARIOS, ids=_SCENARIO_IDS)
    def test_detect_latency(self, benchmark: pytest.fixture, client: httpx.Client, scenario: dict) -> None:
        payload = {"text": scenario["text"], "mode": scenario["mode"]}
        result = benchmark(client.post, "/detect", json=payload)
        assert result.status_code == 200


# ── concurrent throughput benchmarks ──────────────────────────────────────────


class TestConcurrentThroughput:
    """Fire N requests in parallel using a thread pool — measures wall-clock time
    for a burst, which reflects server-side concurrency capacity.

    Uses a fresh client per call so connections aren't serialised through the
    session fixture's pool.
    """

    def _burst(self, api_url: str, payload: dict, n: int) -> list[int]:
        """Send N concurrent POST /detect requests; return status codes."""
        def call() -> int:
            return httpx.post(f"{api_url}/detect", json=payload, timeout=30.0).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            return list(pool.map(lambda _: call(), range(n)))

    @pytest.mark.parametrize("n", [5, 10, 25], ids=["5_concurrent", "10_concurrent", "25_concurrent"])
    def test_burst_single_email(self, benchmark: pytest.fixture, api_url: str, n: int) -> None:
        scenario = next(s for s in _SCENARIOS if s["name"] == "single_email")
        payload = {"text": scenario["text"], "mode": "fast"}
        statuses = benchmark(self._burst, api_url, payload, n)
        assert all(s == 200 for s in statuses), f"Some requests failed: {statuses}"

    @pytest.mark.parametrize("n", [5, 10], ids=["5_concurrent", "10_concurrent"])
    def test_burst_loan_application(self, benchmark: pytest.fixture, api_url: str, n: int) -> None:
        scenario = next(s for s in _SCENARIOS if s["name"] == "au_loan_application")
        payload = {"text": scenario["text"], "mode": "fast"}
        statuses = benchmark(self._burst, api_url, payload, n)
        assert all(s == 200 for s in statuses), f"Some requests failed: {statuses}"


# ── mode comparison ────────────────────────────────────────────────────────────


class TestModeComparison:
    """Compare fast vs advisor mode on the same text.

    If an advisor model is not configured the API falls back to fast, so both
    numbers may be identical — that is expected and not a failure.
    """

    def test_fast_mode_latency(self, benchmark: pytest.fixture, client: httpx.Client) -> None:
        scenario = next(s for s in _SCENARIOS if s["name"] == "au_loan_application")
        result = benchmark(client.post, "/detect", json={"text": scenario["text"], "mode": "fast"})
        assert result.status_code == 200

    def test_advisor_mode_latency(self, benchmark: pytest.fixture, client: httpx.Client) -> None:
        scenario = next(s for s in _SCENARIOS if s["name"] == "advisor_ambiguous")
        result = benchmark(client.post, "/detect", json={"text": scenario["text"], "mode": "advisor"})
        assert result.status_code == 200

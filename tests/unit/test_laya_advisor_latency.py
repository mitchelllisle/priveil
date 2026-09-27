"""Benchmark: LayaSpanAdvisor latency.

Measures the wall-clock latency of span verification for a set of realistic
entity payloads. No real model inference — the advisor backend is mocked so
we measure the async orchestration, thread-pool dispatch, and fan-out overhead.

Run with::

    uv run pytest tests/unit/test_laya_advisor_latency.py --benchmark-only -v

For real wall-clock measurements with actual laya inference, set
PRIVEIL_ADVISOR_BACKEND=laya and point at a running server; see
benchmarks/test_throughput.py for the API-level benchmarks.
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import MagicMock

import pytest

from priveil.advisor.laya_advisor import LayaSpanAdvisor
from priveil.domain.entities import Entity, EntityType
from priveil.settings import Settings

# ── test fixtures ─────────────────────────────────────────────────────────────


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _entity(
    text: str,
    entity_type: EntityType,
    start: int,
    verification: str = "advisor",
    score: float = 0.85,
) -> Entity:
    return Entity(
        text=text,
        entity_type=entity_type,
        start=start,
        end=start + len(text),
        score=score,
        is_pii=True,
        sensitivity="medium",
        verification=verification,  # type: ignore[arg-type]
        default_operator="replace",
        default_operator_params={},
    )


# Realistic multi-entity payloads
_PAYLOADS: dict[str, tuple[str, tuple[Entity, ...]]] = {
    "single_advisor_span": (
        "Contact Jane Smith at jane.smith@bank.com.au",
        (
            _entity("Jane Smith", EntityType.PERSON, 8),
        ),
    ),
    "three_advisor_spans": (
        "Jane Smith (jane@example.com, 0412 345 678) applied for a loan",
        (
            _entity("Jane Smith", EntityType.PERSON, 0),
            _entity("jane@example.com", EntityType.EMAIL_ADDRESS, 12),
            _entity("0412 345 678", EntityType.AU_PHONE, 30),
        ),
    ),
    "five_advisor_spans": (
        "John Doe (john@example.com) BSB 062-000 TFN 123 456 782 phone 0412 000 111",
        (
            _entity("John Doe", EntityType.PERSON, 0),
            _entity("john@example.com", EntityType.EMAIL_ADDRESS, 10),
            _entity("062-000", EntityType.AU_BSB, 28),
            _entity("123 456 782", EntityType.AU_TFN, 40),
            _entity("0412 000 111", EntityType.AU_PHONE, 57),
        ),
    ),
    "all_trust_spans": (
        "TFN 123 456 782",
        (
            _entity("123 456 782", EntityType.AU_TFN, 4, verification="trust", score=1.0),
        ),
    ),
}


# ── mock advisors ─────────────────────────────────────────────────────────────


def _laya_advisor(latency_ms: float = 0.0) -> LayaSpanAdvisor:
    """Laya advisor with a mock router that simulates inference latency."""
    executor = ThreadPoolExecutor(max_workers=4)
    s = _settings()

    def _fake_predict(state: Any, questions: Any) -> dict[str, Any]:
        if latency_ms > 0:
            time.sleep(latency_ms / 1000)
        return {"answers": {"is_genuine_pii": {"noul": 0.8}}}

    router = MagicMock()
    router.predict.side_effect = _fake_predict
    return LayaSpanAdvisor(router=router, settings=s, executor=executor)


# ── benchmarks ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("payload_name", list(_PAYLOADS.keys()))
def test_laya_advisor_overhead(benchmark: Any, payload_name: str) -> None:
    """Benchmark laya advisor async orchestration (no inference latency)."""
    text, entities = _PAYLOADS[payload_name]
    advisor = _laya_advisor(latency_ms=0.0)

    def run() -> None:
        asyncio.run(advisor.advise(text, entities))

    benchmark(run)


@pytest.mark.parametrize("payload_name,n_spans", [
    ("single_advisor_span", 1),
    ("three_advisor_spans", 3),
    ("five_advisor_spans", 5),
])
def test_laya_simulated_33ms_per_span(benchmark: Any, payload_name: str, n_spans: int) -> None:
    """Laya at 33ms/span concurrent: total time ≈ 33ms regardless of span count."""
    text, entities = _PAYLOADS[payload_name]
    advisor = _laya_advisor(latency_ms=33.0)

    def run() -> None:
        asyncio.run(advisor.advise(text, entities))

    benchmark(run)

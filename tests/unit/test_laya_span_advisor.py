"""Unit tests for LayaSpanAdvisor.

Tests mirror the structure of test_span_advisor_routing.py so the two backends
can be compared side-by-side. All tests mock the laya Router to avoid loading
any checkpoints — only the advisor logic itself is exercised.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from priveil.advisor.laya_advisor import LayaSpanAdvisor
from priveil.advisor.span_advisor import AdvisorResult
from priveil.domain.entities import Entity, EntityType
from priveil.settings import Settings

# ── test helpers ──────────────────────────────────────────────────────────────


def _settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


def _entity(
    *,
    entity_type: EntityType = EntityType.EMAIL_ADDRESS,
    text: str = "user@example.com",
    start: int = 0,
    score: float = 0.85,
    verification: str = "trust",
) -> Entity:
    sensitivity_map = {
        EntityType.EMAIL_ADDRESS: "medium",
        EntityType.AU_TFN: "critical",
        EntityType.AU_MEDICARE: "critical",
        EntityType.AU_BSB: "high",
        EntityType.AU_ABN: "low",
        EntityType.AU_PHONE: "medium",
        EntityType.CREDIT_CARD: "critical",
    }
    is_pii_map = {
        EntityType.EMAIL_ADDRESS: True,
        EntityType.AU_TFN: True,
        EntityType.AU_MEDICARE: True,
        EntityType.AU_BSB: True,
        EntityType.AU_ABN: False,
        EntityType.AU_PHONE: True,
        EntityType.CREDIT_CARD: True,
    }
    return Entity(
        text=text,
        entity_type=entity_type,
        start=start,
        end=start + len(text),
        score=score,
        is_pii=is_pii_map.get(entity_type, True),
        sensitivity=sensitivity_map.get(entity_type, "medium"),
        verification=verification,  # type: ignore[arg-type]
    )


def _make_router(prob: float = 0.8) -> Any:
    """Return a mock laya Router that returns the given probability for is_genuine_pii."""
    router = MagicMock()
    router.predict.return_value = {"answers": {"is_genuine_pii": {"noul": prob}}}
    return router


def _advisor(*, prob: float = 0.8, **settings_kwargs: object) -> LayaSpanAdvisor:
    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    s = _settings(**settings_kwargs)
    return LayaSpanAdvisor(router=_make_router(prob), settings=s, executor=executor)


# ── routing: trust bypass ──────────────────────────────────────────────────────


class TestTrustBypass:
    """Trust-verified entities must bypass laya exactly as they bypass the LLM advisor."""

    async def test_all_trust_entities_bypass_laya(self) -> None:
        adv = _advisor()
        entities = (
            _entity(entity_type=EntityType.EMAIL_ADDRESS, verification="trust"),
            _entity(entity_type=EntityType.AU_TFN, text="123 456 782", start=20, score=0.95, verification="trust"),
        )
        result = await adv.advise("user@example.com some text 123 456 782", entities)
        adv._router.predict.assert_not_called()
        assert result.advisor_applied is False
        assert len(result.entities) == 2

    async def test_high_score_entity_bypasses_laya(self) -> None:
        """Entities at or above advisor_score_threshold bypass laya even when advisor-routed."""
        adv = _advisor()
        s = _settings()
        entity = _entity(verification="advisor", score=s.advisor_score_threshold)
        result = await adv.advise("some text", (entity,))
        adv._router.predict.assert_not_called()
        assert result.advisor_applied is False
        assert len(result.entities) == 1

    async def test_empty_entities_returns_empty(self) -> None:
        adv = _advisor()
        result = await adv.advise("some text", ())
        adv._router.predict.assert_not_called()
        assert result.advisor_applied is False
        assert len(result.entities) == 0


# ── laya verification routing ──────────────────────────────────────────────────


class TestLayaVerification:
    """Advisor-tier entities should be submitted to laya for verification."""

    async def test_advisor_entity_above_threshold_is_kept(self) -> None:
        adv = _advisor(prob=0.9)  # well above 0.5 default threshold
        entity = _entity(verification="advisor", score=0.5)
        result = await adv.advise("user@example.com", (entity,))
        adv._router.predict.assert_called_once()
        assert result.advisor_applied is True
        assert len(result.entities) == 1

    async def test_advisor_entity_below_threshold_is_dropped(self) -> None:
        adv = _advisor(prob=0.2)  # below 0.5 threshold
        entity = _entity(verification="advisor", score=0.5)
        result = await adv.advise("user@example.com", (entity,))
        assert result.advisor_applied is True
        assert len(result.entities) == 0

    async def test_custom_threshold_respected(self) -> None:
        """laya_pii_threshold setting gates which spans are kept."""
        adv = _advisor(prob=0.6, laya_pii_threshold=0.7)
        entity = _entity(verification="advisor", score=0.5)
        result = await adv.advise("user@example.com", (entity,))
        # prob=0.6 is below threshold=0.7, so span dropped
        assert result.advisor_applied is True
        assert len(result.entities) == 0

    async def test_multiple_spans_run_concurrently(self) -> None:
        """Multiple advisor spans should all be verified (router called per span)."""
        adv = _advisor(prob=0.8)
        entities = (
            _entity(text="user1@example.com", verification="advisor", score=0.5),
            _entity(text="user2@example.com", start=20, verification="advisor", score=0.5),
            _entity(text="user3@example.com", start=40, verification="advisor", score=0.5),
        )
        result = await adv.advise("user1@example.com  user2@example.com  user3@example.com", entities)
        assert adv._router.predict.call_count == 3
        assert result.advisor_applied is True
        assert len(result.entities) == 3

    async def test_mixed_trust_and_advisor_entities(self) -> None:
        """Trust entities pass through; advisor entities go to laya."""
        adv = _advisor(prob=0.8)
        entities = (
            _entity(entity_type=EntityType.AU_TFN, text="123 456 782", start=0, verification="trust"),
            _entity(
                entity_type=EntityType.EMAIL_ADDRESS,
                text="user@example.com",
                start=20,
                verification="advisor",
                score=0.5,
            ),
        )
        result = await adv.advise("123 456 782 user@example.com", entities)
        adv._router.predict.assert_called_once()
        assert result.advisor_applied is True
        assert len(result.entities) == 2


# ── fail-open behaviour ────────────────────────────────────────────────────────


class TestFailOpen:
    """Laya errors must fail-open (keep all spans), mirroring the LLM advisor."""

    async def test_laya_exception_fails_open(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        router = MagicMock()
        router.predict.side_effect = RuntimeError("checkpoint unavailable")
        adv = LayaSpanAdvisor(router=router, settings=_settings(), executor=executor)
        entity = _entity(verification="advisor", score=0.5)
        result = await adv.advise("user@example.com", (entity,))
        # Should not raise; spans kept; advisor_applied=False (fail-open = not verified)
        assert len(result.entities) == 1
        assert result.advisor_applied is False

    async def test_partial_failure_keeps_failed_span(self) -> None:
        """If one span fails, that span is kept; others proceed normally."""
        from concurrent.futures import ThreadPoolExecutor

        call_count = 0

        def _flaky_predict(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first call fails")
            return {"answers": {"is_genuine_pii": {"noul": 0.1}}}

        executor = ThreadPoolExecutor(max_workers=1)
        router = MagicMock()
        router.predict.side_effect = _flaky_predict
        adv = LayaSpanAdvisor(router=router, settings=_settings(), executor=executor)
        entities = (
            _entity(text="span1@example.com", verification="advisor", score=0.5),
            _entity(text="span2@example.com", start=20, verification="advisor", score=0.5),
        )
        result = await adv.advise("span1@example.com span2@example.com", entities)
        # span1: kept (fail-open); span2: prob 0.1 < 0.5, dropped
        # advisor_applied=False because span1 failed — verification was not clean
        assert len(result.entities) == 1
        assert result.entities[0].text == "span1@example.com"
        assert result.advisor_applied is False


# ── output shape ──────────────────────────────────────────────────────────────


class TestOutputShape:
    """AdvisorResult shape must match what routes expect."""

    async def test_result_is_advisor_result(self) -> None:
        adv = _advisor()
        result = await adv.advise("user@example.com", (_entity(verification="trust"),))
        assert isinstance(result, AdvisorResult)
        assert isinstance(result.entities, tuple)
        assert isinstance(result.advisor_applied, bool)

    async def test_merged_result_sorted_by_start_offset(self) -> None:
        adv = _advisor(prob=0.9)
        entities = (
            _entity(
                entity_type=EntityType.EMAIL_ADDRESS,
                text="b@example.com",
                start=20,
                verification="advisor",
                score=0.5,
            ),
            _entity(entity_type=EntityType.AU_TFN, text="123 456 782", start=0, verification="trust"),
        )
        result = await adv.advise("123 456 782 b@example.com", entities)
        starts = [e.start for e in result.entities]
        assert starts == sorted(starts), "Result entities must be sorted by start offset"


# ── build_laya_advisor ────────────────────────────────────────────────────────


class TestBuildLayaAdvisor:
    """build_laya_advisor raises ImportError when laya is not installed."""

    def test_raises_import_error_when_laya_missing(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        with patch.dict("sys.modules", {"laya": None}):  # type: ignore[arg-type]
            with pytest.raises((ImportError, TypeError)):
                from priveil.advisor.laya_advisor import build_laya_advisor

                build_laya_advisor(_settings(), ThreadPoolExecutor(max_workers=1))

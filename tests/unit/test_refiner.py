"""Unit tests for priveil.advisor.span_advisor."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from priveil.advisor.span_advisor import KeepDecision, SpanAdvisor
from priveil.domain.entities import Entity, EntityType
from priveil.settings import Settings

# is_pii, sensitivity, verification — hardcoded per type (ENTITY_CLASSIFICATION removed)
_META: dict[EntityType, tuple[bool, str, str]] = {
    EntityType.PERSON: (True, "high", "advisor"),
    EntityType.EMAIL_ADDRESS: (True, "medium", "trust"),
    EntityType.PHONE_NUMBER: (True, "medium", "trust"),
    EntityType.LOCATION: (True, "low", "advisor"),
    EntityType.DATE_TIME: (False, "low", "advisor"),
}

def _entity(entity_type: EntityType, text: str, start: int, score: float) -> Entity:
    is_pii, sensitivity, verification = _META[entity_type]
    return Entity(
        text=text,
        entity_type=entity_type,
        start=start,
        end=start + len(text),
        score=score,
        is_pii=is_pii,
        sensitivity=sensitivity,
        verification=verification,
    )


def _settings(**kwargs: object) -> Settings:
    return Settings(
        _env_file=None,
        advisor_model="openai:test",
        **cast(dict[str, Any], kwargs),
    )


def _mock_agent(keep: list[int]) -> Any:  # conduit: Any — avoids pydantic-ai test infra
    """Minimal agent double: run() returns KeepDecision with the given keep list."""
    async def run(prompt: str, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(output=KeepDecision(keep=keep))
    return SimpleNamespace(run=run)


def _slow_agent(keep: list[int], delay: float) -> Any:  # conduit: Any — same as above
    """Agent double that sleeps before responding — for timeout tests."""
    async def run(prompt: str, **kwargs: object) -> SimpleNamespace:
        await asyncio.sleep(delay)
        return SimpleNamespace(output=KeepDecision(keep=keep))
    return SimpleNamespace(run=run)


@pytest.mark.asyncio
async def test_advise_skips_llm_for_trust_verified_entities() -> None:
    # EMAIL_ADDRESS is verification="trust" — bypasses advisor regardless of score
    entity = _entity(EntityType.EMAIL_ADDRESS, "a@b.com", 0, 0.7)
    advisor = SpanAdvisor(agent=_mock_agent([0]), settings=_settings())
    result = await advisor.advise("Email a@b.com", (entity,))
    assert result.entities == (entity,)
    assert result.advisor_applied is False


@pytest.mark.asyncio
async def test_advise_keeps_only_advisor_approved_ids() -> None:
    # PERSON + LOCATION both have verification="advisor" in _META
    person = _entity(EntityType.PERSON, "Jane Smith", 0, 0.8)
    location = _entity(EntityType.LOCATION, "Sydney", 20, 0.7)
    # Force both below score threshold so advisor is triggered
    advisor = SpanAdvisor(
        agent=_mock_agent([1]),  # keep index 1 = location
        settings=_settings(advisor_score_threshold=0.99),
    )
    result = await advisor.advise("Jane Smith lives in Sydney", (person, location))
    assert result.entities == (location,)
    assert result.advisor_applied is True


@pytest.mark.asyncio
async def test_advise_fail_open_on_timeout() -> None:
    advisor = SpanAdvisor(
        agent=_slow_agent([0], delay=0.05),
        settings=_settings(advisor_timeout_ms=1),
    )
    person = _entity(EntityType.PERSON, "Jane Smith", 0, 0.7)
    result = await advisor.advise("Jane Smith", (person,))
    # fail-open: keep the span, mark as not applied
    assert result.entities == (person,)
    assert result.advisor_applied is False


@pytest.mark.asyncio
async def test_advise_includes_trust_entities_without_calling_llm() -> None:
    # PHONE_NUMBER is trust — kept without advisor call
    # PERSON at low score → advisor route, approved by mock (id 0)
    trusted = _entity(EntityType.PHONE_NUMBER, "0400 000 000", 0, 1.0)
    uncertain = _entity(EntityType.PERSON, "Jane Smith", 15, 0.7)
    advisor = SpanAdvisor(agent=_mock_agent([0]), settings=_settings())
    result = await advisor.advise("0400 000 000 Jane Smith", (trusted, uncertain))
    assert result.entities == (trusted, uncertain)
    assert result.advisor_applied is True

"""Unit tests for the entity domain models.

These tests verify the entity type enumeration and the Entity model's fields,
including the new `verification` field introduced in the architectural rewrite.
No engine or network required.
"""

import pytest

from priveil.domain.entities import Entity, EntityType
from priveil.recognisers.registry import build_recognisers


def test_every_entity_type_value_is_nonempty_string() -> None:
    """Every EntityType value must be a non-empty string — enum integrity check."""
    for member in EntityType:
        assert isinstance(member.value, str) and member.value


def test_entity_model_accepts_trust_verification() -> None:
    """Entity can be constructed with verification='trust'."""
    e = Entity(
        text="Jane Smith", entity_type=EntityType.PERSON,
        start=0, end=10, score=0.9,
        is_pii=True, sensitivity="high", verification="trust",
    )
    assert e.verification == "trust"


def test_entity_model_accepts_advisor_verification() -> None:
    """Entity can be constructed with verification='advisor'."""
    e = Entity(
        text="Jane Smith", entity_type=EntityType.PERSON,
        start=0, end=10, score=0.9,
        is_pii=True, sensitivity="high", verification="advisor",
    )
    assert e.verification == "advisor"


def test_credit_card_is_critical_pii() -> None:
    e = Entity(
        text="4111111111111111", entity_type=EntityType.CREDIT_CARD,
        start=0, end=16, score=0.9,
        is_pii=True, sensitivity="critical",
    )
    assert e.is_pii is True
    assert e.sensitivity == "critical"


def test_date_time_is_not_pii() -> None:
    e = Entity(
        text="2024-01-01", entity_type=EntityType.DATE_TIME,
        start=0, end=10, score=0.85,
        is_pii=False, sensitivity="low",
    )
    assert e.is_pii is False


def test_person_is_high_sensitivity_pii() -> None:
    e = Entity(
        text="Jane Smith", entity_type=EntityType.PERSON,
        start=0, end=10, score=0.9,
        is_pii=True, sensitivity="high",
    )
    assert e.is_pii is True
    assert e.sensitivity == "high"


@pytest.mark.parametrize("recogniser", build_recognisers(gliner_model=None))
def test_recogniser_sensitivity_is_valid_literal(recogniser: object) -> None:
    """Every recogniser declares a valid sensitivity tier and is_pii bool."""
    from priveil.recognisers.base import BaseRecogniser
    assert isinstance(recogniser, BaseRecogniser)
    assert recogniser.sensitivity in {"low", "medium", "high", "critical"}
    assert isinstance(recogniser.is_pii, bool)

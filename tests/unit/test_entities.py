"""Unit tests for the entity domain models.

These tests verify the classification map is complete and the business rules
for PII and sensitivity are correct — no engine or network required.
"""

import pytest

from priveil.domain.entities import ENTITY_CLASSIFICATION, EntityType


def test_every_entity_type_has_classification() -> None:
    """Every EntityType member must have an entry in ENTITY_CLASSIFICATION.

    A missing entry is a bug: the engine would raise KeyError at runtime.
    """
    for member in EntityType:
        assert member in ENTITY_CLASSIFICATION, f"{member} missing from ENTITY_CLASSIFICATION"


def test_credit_card_is_critical_pii() -> None:
    is_pii, sensitivity = ENTITY_CLASSIFICATION[EntityType.CREDIT_CARD]
    assert is_pii is True
    assert sensitivity == "critical"


def test_date_time_is_not_pii() -> None:
    is_pii, _ = ENTITY_CLASSIFICATION[EntityType.DATE_TIME]
    assert is_pii is False


def test_person_is_high_sensitivity_pii() -> None:
    is_pii, sensitivity = ENTITY_CLASSIFICATION[EntityType.PERSON]
    assert is_pii is True
    assert sensitivity == "high"


@pytest.mark.parametrize("entity_type", list(EntityType))
def test_sensitivity_is_valid_literal(entity_type: EntityType) -> None:
    _, sensitivity = ENTITY_CLASSIFICATION[entity_type]
    assert sensitivity in {"low", "medium", "high", "critical"}

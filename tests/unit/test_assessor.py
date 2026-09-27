"""Unit tests for entity_breakdown — pure function, no LLM."""

from priveil.advisor.laya_assessor import entity_breakdown as _entity_breakdown
from priveil.domain.detection import DetectionResult
from priveil.domain.entities import Entity, EntityType

# Hardcoded classification map (replaces the removed ENTITY_CLASSIFICATION dict).
_CLASSIFICATION: dict[EntityType, tuple[bool, str]] = {
    EntityType.PERSON: (True, "high"),
    EntityType.EMAIL_ADDRESS: (True, "medium"),
    EntityType.PHONE_NUMBER: (True, "medium"),
    EntityType.AU_TFN: (True, "critical"),
    EntityType.AU_ABN: (False, "low"),
}


def _entity(entity_type: EntityType, text: str, start: int = 0) -> Entity:
    is_pii, sensitivity = _CLASSIFICATION[entity_type]
    return Entity(
        text=text,
        entity_type=entity_type,
        start=start,
        end=start + len(text),
        score=0.9,
        is_pii=is_pii,
        sensitivity=sensitivity,
        verification="trust",
        default_operator="replace",
        default_operator_params={},
    )


def _detections(*entities: Entity, text: str = "test") -> DetectionResult:
    return DetectionResult.from_text(text=text, entities=list(entities))


# ── _entity_breakdown ─────────────────────────────────────────────────────────

def test_breakdown_counts_by_type() -> None:
    detections = _detections(
        _entity(EntityType.EMAIL_ADDRESS, "a@b.com", 0),
        _entity(EntityType.EMAIL_ADDRESS, "c@d.com", 10),
        _entity(EntityType.PERSON, "Jane", 20),
    )
    breakdown = _entity_breakdown(detections)
    counts = {b.entity_type: b.count for b in breakdown}
    assert counts["PERSON"] == 1
    assert counts["EMAIL_ADDRESS"] == 2  # noqa: PLR2004


def test_breakdown_excludes_non_pii() -> None:
    detections = _detections(
        _entity(EntityType.AU_ABN, "51 824 753 556", 0),  # is_pii=False
        _entity(EntityType.EMAIL_ADDRESS, "a@b.com", 20),
    )
    breakdown = _entity_breakdown(detections)
    types = {b.entity_type for b in breakdown}
    assert "AU_ABN" not in types
    assert "EMAIL_ADDRESS" in types


def test_breakdown_empty_when_no_pii() -> None:
    detections = _detections(text="The rate is 4.5% p.a.")
    assert _entity_breakdown(detections) == []


def test_breakdown_sensitivity_from_classification() -> None:
    detections = _detections(
        _entity(EntityType.AU_TFN, "123 456 782", 0),
    )
    breakdown = _entity_breakdown(detections)
    assert breakdown[0].sensitivity == "critical"

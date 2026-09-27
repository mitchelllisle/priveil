"""Unit tests for LayaAssessor.

Verifies _derive_assess_result logic and LayaAssessor.assess() end-to-end
with a mocked laya Router. No real model inference.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from priveil.advisor.laya_assessor import LayaAssessor, _derive_assess_result
from priveil.domain.assessment import AssessmentData
from priveil.domain.detection import DetectionResult
from priveil.domain.entities import Entity, EntityType

# ── test helpers ──────────────────────────────────────────────────────────────


def _entity(
    entity_type: EntityType,
    text: str = "value",
    start: int = 0,
    is_pii: bool = True,
    sensitivity: str = "medium",
) -> Entity:
    return Entity(
        text=text,
        entity_type=entity_type,
        start=start,
        end=start + len(text),
        score=0.9,
        is_pii=is_pii,
        sensitivity=sensitivity,
        verification="trust",
    )

def _detections(*entities: Entity, input_hash: str = "hmac-sha256:abc") -> DetectionResult:
    return DetectionResult(
        entities=entities,
        input_hash=input_hash,
    )

def _laya_answers(
    sensitivity: str = "medium",
    is_financial: float = 0.1,
    is_identity: float = 0.1,
    is_medical: float = 0.1,
    is_employment: float = 0.1,
) -> dict[str, Any]:
    return {
        "overall_sensitivity": {"choice": sensitivity},
        "is_financial": {"noul": is_financial},
        "is_identity": {"noul": is_identity},
        "is_medical": {"noul": is_medical},
        "is_employment": {"noul": is_employment},
    }


def _assessor(answers: dict[str, Any] | None = None) -> LayaAssessor:
    from concurrent.futures import ThreadPoolExecutor

    router = MagicMock()
    router.predict.return_value = {"answers": answers or _laya_answers()}
    return LayaAssessor(router=router, executor=ThreadPoolExecutor(max_workers=1))


# ── _derive_assess_result ─────────────────────────────────────────────────────


class TestDeriveAssessResult:
    """Pure unit tests for the rule-based derivation function."""

    def test_sensitivity_passed_through(self) -> None:
        answers = _laya_answers(sensitivity="critical")
        result = _derive_assess_result(answers, _detections())
        assert result.overall_sensitivity == "critical"

    def test_financial_category_from_noul(self) -> None:
        answers = _laya_answers(is_financial=0.9)
        result = _derive_assess_result(answers, _detections())
        assert "financial" in result.categories

    def test_identity_category_from_noul(self) -> None:
        answers = _laya_answers(is_identity=0.8)
        result = _derive_assess_result(answers, _detections())
        assert "identity" in result.categories

    def test_medical_category_from_noul(self) -> None:
        answers = _laya_answers(is_medical=0.7)
        result = _derive_assess_result(answers, _detections())
        assert "medical" in result.categories

    def test_employment_category_from_noul(self) -> None:
        answers = _laya_answers(is_employment=0.6)
        result = _derive_assess_result(answers, _detections())
        assert "employment" in result.categories

    def test_below_threshold_not_categorised(self) -> None:
        answers = _laya_answers(is_financial=0.4, is_identity=0.3)
        result = _derive_assess_result(answers, _detections())
        assert "financial" not in result.categories
        assert "identity" not in result.categories

    def test_au_tfn_forces_financial_and_identity_categories(self) -> None:
        """AU_TFN entity should force both financial and identity regardless of noul."""
        detections = _detections(
            _entity(EntityType.AU_TFN, "123 456 782", sensitivity="critical")
        )
        answers = _laya_answers(is_financial=0.1, is_identity=0.1)
        result = _derive_assess_result(answers, detections)
        assert "financial" in result.categories
        assert "identity" in result.categories

    def test_regulatory_flags_for_financial_category(self) -> None:
        answers = _laya_answers(is_financial=0.9)
        result = _derive_assess_result(answers, _detections())
        assert any("ATO" in flag for flag in result.regulatory_flags)

    def test_no_pii_no_categories_returns_privacy_act(self) -> None:
        answers = _laya_answers(sensitivity="high")
        result = _derive_assess_result(answers, _detections())
        # High sensitivity with no categories: falls back to Privacy Act
        assert result.regulatory_flags  # at least one flag

    def test_result_is_assessment_data(self) -> None:
        result = _derive_assess_result(_laya_answers(), _detections())
        assert isinstance(result, AssessmentData)

    def test_reasoning_mentions_laya(self) -> None:
        result = _derive_assess_result(_laya_answers(), _detections())
        assert "laya" in result.reasoning.lower() or "Laya" in result.reasoning

    def test_entity_breakdown_populated_from_detections(self) -> None:
        detections = _detections(
            _entity(EntityType.AU_TFN, "123 456 782", sensitivity="critical"),
            _entity(EntityType.EMAIL_ADDRESS, "a@b.com", sensitivity="medium"),
        )
        result = _derive_assess_result(_laya_answers(), detections)
        types = {b.entity_type for b in result.entity_breakdown}
        assert "AU_TFN" in types
        assert "EMAIL_ADDRESS" in types

    def test_handling_guidance_is_non_empty(self) -> None:
        for sensitivity in ("low", "medium", "high", "critical"):
            result = _derive_assess_result(_laya_answers(sensitivity=sensitivity), _detections())
            assert len(result.recommended_handling) > 10


# ── LayaAssessor.assess ───────────────────────────────────────────────────────


class TestLayaAssessor:
    """Integration tests for the LayaAssessor class."""

    async def test_returns_assessment_data(self) -> None:
        assessor = _assessor()
        detections = _detections()
        result = await assessor.assess("Sample text.", detections)
        assert isinstance(result, AssessmentData)

    async def test_router_called_with_state_and_questions(self) -> None:
        assessor = _assessor()
        await assessor.assess("Sample text.", _detections())
        assessor._router.predict.assert_called_once()

    async def test_high_sensitivity_answer_propagated(self) -> None:
        answers = _laya_answers(sensitivity="critical", is_financial=0.95, is_identity=0.85)
        assessor = _assessor(answers)
        result = await assessor.assess("TFN 123 456 782", _detections())
        assert result.overall_sensitivity == "critical"
        assert "financial" in result.categories
        assert "identity" in result.categories

    async def test_raises_on_laya_error(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        router = MagicMock()
        router.predict.side_effect = RuntimeError("laya failure")
        assessor = LayaAssessor(router=router, executor=ThreadPoolExecutor(max_workers=1))
        with pytest.raises(RuntimeError):
            await assessor.assess("text", _detections())

    async def test_state_includes_pii_entity_types(self) -> None:
        """Router state dict should include detected PII types for context."""
        assessor = _assessor()
        detections = _detections(
            _entity(EntityType.AU_TFN, "123 456 782", sensitivity="critical"),
        )
        await assessor.assess("TFN 123 456 782", detections)
        call_args = assessor._router.predict.call_args
        state = call_args[0][0]
        assert "AU_TFN" in state["entities"]

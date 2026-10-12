"""Judge assessor for /assess.

Uses a Type-1 non-autoregressive model (laya) with typed questions to assess
text sensitivity. Returns the same ``AssessmentData`` shape as an LLM assessor;
text-generation fields (risk_summary, regulatory_flags, recommended_handling,
reasoning) are derived from typed answers plus entity-based rule tables.

Typical latency: ~33 ms on GPU, ~80-150 ms on CPU. No API key required.

Requires: uv sync --extra laya
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from priveil.domain.assessment import AssessmentData, EntityBreakdown
from priveil.domain.detection import DetectionResult

logger = logging.getLogger(__name__)


def entity_breakdown(detections: DetectionResult) -> list[EntityBreakdown]:
    """Compute entity_breakdown from detections. Pure function."""
    type_info: dict[str, tuple[str, int]] = {}
    for entity in detections.entities:
        if not entity.is_pii:
            continue
        et = entity.entity_type.value
        sensitivity, count = type_info.get(et, (entity.sensitivity, 0))
        type_info[et] = (sensitivity, count + 1)
    return [
        EntityBreakdown(entity_type=et, sensitivity=sensitivity, count=count)
        for et, (sensitivity, count) in sorted(type_info.items(), key=lambda x: -x[1][1])
    ]

# ── question schema ───────────────────────────────────────────────────────────

_ASSESS_QUESTIONS: dict[str, Any] = {
    "overall_sensitivity": {
        "type": "choice",
        "instructions": (
            "What is the overall PII sensitivity level of this text "
            "based on the detected entities and their regulatory status?"
        ),
        "criteria": {
            "low": "No identifiable personal information; entity data is non-sensitive (e.g. company ABN)",
            "medium": "Some personal contact information present (email, phone number)",
            "high": "Sensitive financial or personal identifiers present (BSB, bank account)",
            "critical": "Highly regulated personal information present (TFN, Medicare, credit card number)",
        },
    },
    "is_financial": {
        "type": "noul",
        "instructions": (
            "Does this text contain financial PII? "
            "(Tax File Number, bank account, credit card, BSB, invoice amounts tied to a person)"
        ),
    },
    "is_identity": {
        "type": "noul",
        "instructions": (
            "Does this text contain identity PII? "
            "(full name, date of birth, government-issued ID, home address, Medicare number)"
        ),
    },
    "is_medical": {
        "type": "noul",
        "instructions": (
            "Does this text contain medical or health information? "
            "(diagnoses, prescriptions, health fund details, disability information)"
        ),
    },
    "is_employment": {
        "type": "noul",
        "instructions": (
            "Does this text contain employment or HR information? "
            "(salary, payslip, performance review, superannuation)"
        ),
    },
}

# ── rule-based helpers ────────────────────────────────────────────────────────


_REGULATORY_FLAGS: dict[str, list[str]] = {
    "financial": ["Privacy Act s16B", "ATO data standards"],
    "identity": ["Privacy Act 1988 (Cth)", "Australian Privacy Principles (APP) 10-11"],
    "medical": ["Privacy Act 1988 (Cth)", "Australian Privacy Principles (APP) 3", "My Health Records Act 2012"],
    "employment": ["Privacy Act 1988 (Cth)", "Fair Work Act 2009"],
}

_HANDLING_BY_SENSITIVITY: dict[str, str] = {
    "low": "Standard data handling applies; public-facing disclosure may be permissible.",
    "medium": (
        "Restrict to authorised staff. Do not include in logs or analytics pipelines. "
        "Apply access controls."
    ),
    "high": (
        "Treat as sensitive personal information. Encrypt at rest. Restrict to need-to-know. "
        "Audit access. Purge when no longer needed."
    ),
    "critical": (
        "Highest risk — handle under strict data-minimisation principles. "
        "Encrypt at rest and in transit. Restrict to minimum necessary staff. "
        "Log all access. Purge within 90 days unless legally required to retain."
    ),
}


def _build_risk_summary(
    sensitivity: str,
    categories: list[str],
    entity_types: list[str],
) -> str:
    if not categories:
        return f"No PII categories detected; overall sensitivity is {sensitivity}."
    cats = " and ".join(categories)
    types_str = ", ".join(entity_types[:3]) if entity_types else "unknown"
    return (
        f"Contains {cats} PII ({types_str}). "
        f"Overall sensitivity: {sensitivity}."
    )


def _derive_assess_result(
    answers: dict[str, Any],
    detections: DetectionResult,
) -> AssessmentData:
    """Convert judge typed answers + detections into AssessmentData."""
    sensitivity: Literal["low", "medium", "high", "critical"] = answers["overall_sensitivity"]["choice"]

    # Categories from noul answers (threshold 0.5)
    categories: list[str] = []
    if answers["is_financial"]["noul"] >= 0.5:
        categories.append("financial")
    if answers["is_identity"]["noul"] >= 0.5:
        categories.append("identity")
    if answers["is_medical"]["noul"] >= 0.5:
        categories.append("medical")
    if answers["is_employment"]["noul"] >= 0.5:
        categories.append("employment")

    # Entity-level categories can override/supplement judge answers
    pii_types = [e.entity_type.value for e in detections.entities if e.is_pii]
    if any(t in {"AU_TFN", "CREDIT_CARD", "AU_BSB", "AU_MEDICARE"} for t in pii_types):
        if "financial" not in categories:
            categories.append("financial")
    if any(t in {"AU_TFN", "AU_MEDICARE"} for t in pii_types):
        if "identity" not in categories:
            categories.append("identity")

    # Regulatory flags — union of per-category flags
    reg_flags: list[str] = []
    seen: set[str] = set()
    for cat in categories:
        for flag in _REGULATORY_FLAGS.get(cat, []):
            if flag not in seen:
                reg_flags.append(flag)
                seen.add(flag)
    if not reg_flags and sensitivity in ("high", "critical"):
        reg_flags = ["Privacy Act 1988 (Cth)"]

    breakdown = entity_breakdown(detections)
    risk_summary = _build_risk_summary(sensitivity, categories, pii_types)
    recommended_handling = _HANDLING_BY_SENSITIVITY[sensitivity]
    reasoning = (
        f"Judge assess: sensitivity={sensitivity}, categories={categories}, "
        f"detected_pii_types={pii_types}. "
        "This result is rule-derived from judge typed decisions and detected entity types; "
        "for detailed regulatory analysis use PRIVEIL_ASSESS_BACKEND=llm."
    )
    return AssessmentData(
        overall_sensitivity=sensitivity,
        risk_summary=risk_summary,
        categories=categories,
        regulatory_flags=reg_flags,
        recommended_handling=recommended_handling,
        entity_breakdown=breakdown,
        reasoning=reasoning,
    )


# ── judge assessor class ──────────────────────────────────────────────────────


class JudgeAssessor:
    """Assessor using a Type-1 non-autoregressive model — no LLM, no API key required.

    Asks typed questions about the text using the judge Router (laya) and derives
    AssessmentData from calibrated noul/choice answers + entity rule tables.
    """

    def __init__(self, router: Any, executor: ThreadPoolExecutor) -> None:
        self._router = router
        self._executor = executor

    async def assess(
        self,
        text: str,
        detections: DetectionResult,
        context: str | None = None,
    ) -> AssessmentData:
        """Run judge assessment and return AssessmentData.

        Args:
            text: The full document text.
            detections: Pre-computed entity detections.
            context: Optional domain context (e.g. 'home loan application').

        Returns:
            AssessmentData with sensitivity, categories, and derived advisory fields.
        """
        loop = asyncio.get_running_loop()
        state: dict[str, Any] = {
            "text": text,
            "entities": [e.entity_type.value for e in detections.entities if e.is_pii],
        }
        if context:
            state["context"] = context

        try:
            result = await loop.run_in_executor(
                self._executor,
                lambda: self._router.predict(state, _ASSESS_QUESTIONS),
            )
            return _derive_assess_result(result["answers"], detections)
        except Exception:
            logger.exception("Judge assess failed; re-raising (not fail-open for assess)")
            raise


def build_judge_assessor(executor: ThreadPoolExecutor, preload: bool = False) -> JudgeAssessor:
    """Build a JudgeAssessor. Raises ImportError if laya is not installed."""
    from laya import Router  # noqa: PLC0415

    router = Router(preload=preload)
    logger.info("Judge assessor loaded (preload=%s)", preload)
    return JudgeAssessor(router=router, executor=executor)

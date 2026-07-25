"""LLM assessor for /assess.

Wraps the pydantic-ai Agent that produces risk and sensitivity assessments.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from priveil.settings import Settings

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from priveil.domain.assessment import AssessmentData, AssessmentRequest, EntityBreakdown
from priveil.domain.detection import DetectionResult

# ── LLM adapter type ──────────────────────────────────────────────────────────

class AssessmentDecision(BaseModel):
    """Raw structured output from the assessor agent."""

    overall_sensitivity: Literal["low", "medium", "high", "critical"] = Field(
        description="Highest sensitivity tier of any detected entity"
    )
    risk_summary: str = Field(description="One-sentence summary of the risk profile")
    categories: list[str] = Field(description="Applicable risk categories")
    regulatory_flags: list[str] = Field(description="Applicable regulatory frameworks")
    recommended_handling: str = Field(description="Actionable handling recommendation")
    reasoning: str = Field(description="Brief explanation of the assessment")


_PROMPTS_DIR = Path(__file__).parent / "prompts"
ASSESSOR_SYSTEM_PROMPT: str = (_PROMPTS_DIR / "assessor.md").read_text(encoding="utf-8").strip()
ASSESSMENT_ADVISORY_DISCLAIMER = (
    "Regulatory flags and recommendations are LLM-generated advisory hints only, not legal determinations."
)


def _build_assessment_prompt(request: AssessmentRequest, detections: DetectionResult) -> str:
    """Build the LLM prompt for the assessor agent.

    Returns a formatted string containing the text, optional context,
    and a JSON array of detected entities.
    """
    entities_json = json.dumps(
        [
            {
                "type": e.entity_type.value,
                "span": e.text,
                "score": round(e.score, 3),
            }
            for e in detections.entities
            if e.is_pii
        ],
        indent=2,
    )
    context_block = f"\nAdditional context: {request.context}\n" if request.context else ""
    return f"""Text to assess:
{request.text}
{context_block}
Detected entities:
{entities_json}"""


def _entity_breakdown(detections: DetectionResult) -> list[EntityBreakdown]:
    """Compute entity_breakdown from detections. Pure function — no LLM."""
    # Only PII entities appear in the breakdown; sensitivity comes from the entity itself.
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


def build_assessor_agent(settings: Settings) -> Agent[None, AssessmentDecision]:
    """Build the assessor agent from application settings."""
    from priveil.advisor.model import build_advisor_model
    return Agent(
        model=build_advisor_model(settings),
        output_type=AssessmentDecision,
        system_prompt=ASSESSOR_SYSTEM_PROMPT,
        model_settings={"temperature": settings.advisor_temperature},
    )


async def assess(
    request: AssessmentRequest,
    detections: DetectionResult,
    agent: Agent[None, AssessmentDecision],
) -> AssessmentData:
    """Run the LLM assessor and return an AssessmentResult.

    Args:
        request: The assessment request (text + optional context).
        detections: Pre-computed or auto-detected entities.
        agent: The assessor Agent instance.

    Returns:
        AssessmentData with risk profile and entity breakdown.
        The advisory disclaimer is not included here — the route adds it to
        ``meta.response.advisory_disclaimer``.
    """
    prompt = _build_assessment_prompt(request, detections)
    result = await agent.run(prompt)
    decision = result.output
    return AssessmentData(
        overall_sensitivity=decision.overall_sensitivity,
        risk_summary=decision.risk_summary,
        categories=decision.categories,
        regulatory_flags=decision.regulatory_flags,
        recommended_handling=decision.recommended_handling,
        entity_breakdown=_entity_breakdown(detections),
        reasoning=decision.reasoning,
    )

"""LLM assessor for /assess.

Produces a risk profile of a piece of text: sensitivity tier, regulatory
exposure, and handling guidance. Separate from the internal refiner.
"""

import json
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from alias.domain.assessment import AssessmentRequest, AssessmentResult, EntityBreakdown
from alias.domain.detection import DetectionResult

# ── LLM adapter type ──────────────────────────────────────────────────────────

class AssessmentDecision(BaseModel):
    """Raw structured output from the assessor agent."""

    overall_sensitivity: Literal["low", "medium", "high", "critical"] = Field(
        description="Highest sensitivity tier of any entity present, or 'low' if none"
    )
    risk_summary: str = Field(description="One or two sentence plain-English risk summary")
    categories: list[str] = Field(
        description="Risk categories present, e.g. ['identity', 'financial', 'health', 'contact']"
    )
    regulatory_flags: list[str] = Field(
        description="Applicable Australian regulatory frameworks, e.g. ['Privacy Act s16B', 'AML-CTF Act s84']"
    )
    recommended_handling: str = Field(
        description="Concrete data handling guidance for this content"
    )
    reasoning: str = Field(description="Brief explanation of the assessment")


ASSESSOR_SYSTEM_PROMPT = """
You are a data governance specialist for Australian financial services.

Given a piece of text and its detected PII entities, produce a risk assessment
that helps the caller understand how sensitive the content is and how to handle it.

## Sensitivity tiers
- critical — TFN, Medicare number, credit card, biometric data
- high     — full name + account number, BSB, passport, driver licence
- medium   — email, phone, address, partial financial identifiers
- low      — ABN/ACN (business identifiers), publicly available info, no PII

## Australian regulatory context
| Framework          | Trigger                                                  |
|--------------------|----------------------------------------------------------|
| Privacy Act s16B   | Sensitive information (health, financial, identity)      |
| AML-CTF Act s84    | Financial transaction records with customer identifiers  |
| CDR Rules          | Consumer banking data shared under Open Banking          |
| APRA CPS 234       | Information security — critical data assets              |
| ATO data standards | Tax file numbers — strict handling and storage controls  |

## Categories
Use from: identity, financial, health, contact, legal, biometric

## Instructions
- Set overall_sensitivity to the highest tier of any entity present.
- Only flag regulatory frameworks that genuinely apply.
- recommended_handling should be specific and actionable.
- reasoning should be one short paragraph.
""".strip()


def _build_assessment_prompt(request: AssessmentRequest, detections: DetectionResult) -> str:
    entities_json = json.dumps(
        [
            {
                "text": e.text,
                "entity_type": e.entity_type.value,
                "is_pii": e.is_pii,
                "sensitivity": e.sensitivity,
            }
            for e in detections.entities
            if e.is_pii
        ],
        indent=2,
    )
    context_line = f"\nContext: {request.context}" if request.context else ""
    return f"""Assess the risk profile of the following text.{context_line}

Text:
\"\"\"{request.text}\"\"\"

Detected PII entities:
{entities_json}"""


def _entity_breakdown(detections: DetectionResult) -> list[EntityBreakdown]:
    """Compute entity_breakdown from detections. Pure function — no LLM."""
    counts: Counter[tuple[str, str]] = Counter(
        (e.entity_type.value, e.sensitivity)
        for e in detections.entities
        if e.is_pii
    )
    return [
        EntityBreakdown(entity_type=entity_type, sensitivity=sensitivity, count=count)
        for (entity_type, sensitivity), count in sorted(counts.items())
    ]


def build_assessor_agent(model: str, temperature: float = 0.0) -> Agent[None, AssessmentDecision]:
    """Build the assessor agent."""
    return Agent(
        model=model,
        output_type=AssessmentDecision,
        system_prompt=ASSESSOR_SYSTEM_PROMPT,
        model_settings={"temperature": temperature},
    )


async def assess(
    request: AssessmentRequest,
    detections: DetectionResult,
    agent: Agent[None, AssessmentDecision],
) -> AssessmentResult:
    """Run the LLM assessor and return an AssessmentResult.

    Args:
        request: The assessment request (text + optional context).
        detections: Pre-computed or auto-detected entities.
        agent: The assessor Agent instance.

    Returns:
        AssessmentResult with risk profile and entity breakdown.
    """
    prompt = _build_assessment_prompt(request, detections)
    result = await agent.run(prompt)
    decision = result.output
    return AssessmentResult(
        overall_sensitivity=decision.overall_sensitivity,
        risk_summary=decision.risk_summary,
        categories=decision.categories,
        regulatory_flags=decision.regulatory_flags,
        recommended_handling=decision.recommended_handling,
        entity_breakdown=_entity_breakdown(detections),
        reasoning=decision.reasoning,
    )

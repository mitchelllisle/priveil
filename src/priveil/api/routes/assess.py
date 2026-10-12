from fastapi import APIRouter, HTTPException

from priveil.api.deps import AnalyserDep, JudgeAssessorDep
from priveil.api.models import Meta, PriveilResponse, RequestMeta, ResponseMeta
from priveil.domain.assessment import AssessmentData, AssessmentRequest
from priveil.domain.detection import DetectionRequest

router = APIRouter()

_JUDGE_ADVISORY_DISCLAIMER = (
    "Sensitivity and categories derived from judge typed decisions; "
    "regulatory flags and handling guidance are rule-derived, not LLM-generated. "
    "Use PRIVEIL_ASSESS_BACKEND=llm for full advisory text."
)


@router.post("", response_model=PriveilResponse[AssessmentData], summary="Assess content risk and sensitivity")
async def assess_content(
    request: AssessmentRequest,
    analyser: AnalyserDep,
    judge_assessor: JudgeAssessorDep,
) -> PriveilResponse[AssessmentData]:
    """Assess the risk profile of a piece of text.

    Returns an overall sensitivity tier, risk categories, applicable Australian
    regulatory frameworks, recommended handling guidance, and a per-entity-type
    breakdown.

    Backend selection (controlled by ``PRIVEIL_ASSESS_BACKEND``):

    - ``laya`` (local, no API key) — sensitivity via judge typed decisions;
      regulatory/handling fields are rule-derived. Requires ``uv sync --extra laya``.
    - ``auto`` (default) — laya if available, else 503.

    Pass ``body["data"]`` from a prior ``/detect`` response as ``detections``.
    """
    if request.detections is not None:
        detections = analyser.detections_from_entities(request.text, request.detections.entities)
    else:
        detections = await analyser.analyse(DetectionRequest(text=request.text))

    if judge_assessor is not None:
        data = await judge_assessor.assess(request.text, detections, context=request.context)
        return PriveilResponse(
            meta=Meta(
                request=RequestMeta(),
                response=ResponseMeta(
                    input_hash=detections.input_hash,
                    advisory_disclaimer=_JUDGE_ADVISORY_DISCLAIMER,
                ),
            ),
            data=data,
        )

    raise HTTPException(
        status_code=503,
        detail=(
            "Assessment not available — install laya (uv sync --extra laya) "
            "or set PRIVEIL_JUDGE_MODEL to enable."
        ),
    )

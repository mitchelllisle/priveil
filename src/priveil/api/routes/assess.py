from fastapi import APIRouter

from priveil.api.deps import AnalyserDep, AssessorDep
from priveil.api.models import Meta, PriveilResponse, RequestMeta, ResponseMeta
from priveil.domain.assessment import AssessmentData, AssessmentRequest
from priveil.domain.detection import DetectionRequest
from priveil.judge.assessor import ASSESSMENT_ADVISORY_DISCLAIMER, assess

router = APIRouter()


@router.post("", response_model=PriveilResponse[AssessmentData], summary="Assess content risk and sensitivity")
async def assess_content(
    request: AssessmentRequest,
    analyser: AnalyserDep,
    assessor: AssessorDep,
) -> PriveilResponse[AssessmentData]:
    """Assess the risk profile of a piece of text.

    Returns an overall sensitivity tier, risk categories, applicable Australian
    regulatory frameworks, recommended handling guidance, and a per-entity-type
    breakdown. Requires PRIVEIL_JUDGE_MODEL to be configured.

    Pass ``body["data"]`` from a prior ``/detect`` response as ``detections``.
    """
    if request.detections is not None:
        detections = analyser.detections_from_entities(request.text, request.detections.entities)
    else:
        detections = await analyser.analyse(DetectionRequest(text=request.text))

    data = await assess(request, detections, assessor)
    return PriveilResponse(
        meta=Meta(
            request=RequestMeta(),
            response=ResponseMeta(
                input_hash=detections.input_hash,
                advisory_disclaimer=ASSESSMENT_ADVISORY_DISCLAIMER,
            ),
        ),
        data=data,
    )

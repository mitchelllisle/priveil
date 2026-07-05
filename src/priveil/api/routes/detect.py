import logging

from fastapi import APIRouter

from priveil.api.deps import AdvisorDep, AnalyserDep
from priveil.api.models import Meta, PriveilResponse, RequestMeta, ResponseMeta
from priveil.domain.detection import DetectionData, DetectionRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=PriveilResponse[DetectionData], summary="Detect PII entities in text")
async def detect(
    request: DetectionRequest,
    analyser: AnalyserDep,
    advisor: AdvisorDep,
) -> PriveilResponse[DetectionData]:
    """Run entity detection on the provided text.

    Returns detected entities with type, offsets, confidence, PII classification,
    and sensitivity level. Includes an HMAC-SHA-256 audit hash in meta.response.

    When mode='advisor' (default) and an advisor model is configured, an LLM pass
    removes false positives before returning. mode='fast' skips the LLM entirely.
    """
    result = await analyser.analyse(request)
    mode_used = request.mode
    advisor_applied = False
    if request.mode == "advisor" and advisor is not None:
        refined = await advisor.advise(request.text, result.entities)
        result = result.model_copy(update={"entities": refined.entities})
        advisor_applied = refined.advisor_applied
    elif request.mode == "advisor":
        mode_used = "fast"
        logger.warning(
            "mode='advisor' requested for /detect but PRIVEIL_ADVISOR_MODEL is unset; falling back to mode='fast'."
        )
    return PriveilResponse(
        meta=Meta(
            request=RequestMeta(mode=request.mode),
            response=ResponseMeta(mode=mode_used, input_hash=result.input_hash),
        ),
        data=DetectionData(entities=result.entities, advisor_applied=advisor_applied),
    )

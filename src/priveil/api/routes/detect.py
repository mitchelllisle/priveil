import logging

from fastapi import APIRouter

from priveil.api.deps import AnalyserDep, RefinerDep
from priveil.api.models import Meta, PriveilResponse, RequestMeta, ResponseMeta
from priveil.domain.detection import DetectionData, DetectionRequest
from priveil.judge.refiner import refine

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=PriveilResponse[DetectionData], summary="Detect PII entities in text")
async def detect(
    request: DetectionRequest,
    analyser: AnalyserDep,
    refiner: RefinerDep,
) -> PriveilResponse[DetectionData]:
    """Run entity detection on the provided text.

    Returns detected entities with type, offsets, confidence, PII classification,
    and sensitivity level. Includes an HMAC-SHA-256 audit hash in meta.response.

    When mode='judge' (default) and a judge model is configured, an LLM pass
    removes false positives before returning. mode='fast' skips the LLM entirely.
    """
    result = await analyser.analyse(request)
    mode_used = request.mode
    if request.mode == "judge" and refiner is not None:
        result = await refine(result, request.text, refiner)
    elif request.mode == "judge":
        mode_used = "fast"
        logger.warning(
            "mode='judge' requested for /detect but PRIVEIL_JUDGE_MODEL is unset; falling back to mode='fast'."
        )
    return PriveilResponse(
        meta=Meta(
            request=RequestMeta(mode=request.mode),
            response=ResponseMeta(mode=mode_used, input_hash=result.input_hash),
        ),
        data=DetectionData(entities=result.entities),
    )

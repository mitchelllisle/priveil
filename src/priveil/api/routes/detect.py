import logging

from fastapi import APIRouter

from priveil.api.deps import JudgeDep, AnalyserDep
from priveil.api.models import Meta, PriveilResponse, RequestMeta, ResponseMeta
from priveil.domain.detection import DetectionData, DetectionRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=PriveilResponse[DetectionData], summary="Detect PII entities in text")
async def detect(
    request: DetectionRequest,
    analyser: AnalyserDep,
    judge: JudgeDep,
) -> PriveilResponse[DetectionData]:
    """Run entity detection on the provided text.

    Returns detected entities with type, offsets, confidence, PII classification,
    and sensitivity level. Includes an HMAC-SHA-256 audit hash in meta.response.

    When mode='judge' (default) and a judge model is configured, a fast judge pass
    removes false positives before returning. mode='fast' skips the judge entirely.
    """
    result = await analyser.analyse(request)
    mode_used = request.mode
    judge_applied = False
    if request.mode == "judge" and judge is not None:
        refined = await judge.judge(request.text, result.entities)
        result = result.model_copy(update={"entities": refined.entities})
        judge_applied = refined.judge_applied
    elif request.mode == "judge":
        mode_used = "fast"
        logger.warning(
            "mode='judge' requested for /detect but no judge is configured; falling back to mode='fast'."
        )
    return PriveilResponse(
        meta=Meta(
            request=RequestMeta(mode=request.mode),
            response=ResponseMeta(mode=mode_used, input_hash=result.input_hash),
        ),
        data=DetectionData(entities=result.entities, judge_applied=judge_applied),
    )

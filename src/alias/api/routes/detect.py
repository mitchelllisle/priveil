from fastapi import APIRouter

from alias.api.deps import AnalyserDep
from alias.domain.detection import DetectionRequest, DetectionResult

router = APIRouter()


@router.post("", response_model=DetectionResult, summary="Detect PII entities in text")
async def detect(request: DetectionRequest, analyser: AnalyserDep) -> DetectionResult:
    """Run entity detection on the provided text.

    Returns all detected entities with their type, character offsets, confidence
    score, PII classification, and sensitivity level. The response also includes
    a SHA-256 audit hash of the original input.
    """
    return await analyser.analyse(request)

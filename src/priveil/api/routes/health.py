from fastapi import APIRouter
from pydantic import BaseModel

from priveil.api.models import Meta, PriveilResponse, RequestMeta, ResponseMeta

router = APIRouter(tags=["health"])


class HealthData(BaseModel, frozen=True):
    status: str


@router.get("/health", response_model=PriveilResponse[HealthData])
async def health() -> PriveilResponse[HealthData]:
    """Liveness check."""
    return PriveilResponse(
        meta=Meta(request=RequestMeta(), response=ResponseMeta()),
        data=HealthData(status="ok"),
    )

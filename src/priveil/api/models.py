"""Response envelope shared across all Priveil API endpoints.

Every response has the shape::

    {
      "meta": {
        "request": { "mode": "judge" },
        "response": { "mode": "fast", "input_hash": "hmac-sha256:..." }
      },
      "data": { ... }
    }

``meta.request`` reflects what the caller asked for;
``meta.response`` describes what was actually produced (mode may differ
on judge-fallback; input_hash and advisory_disclaimer appear where applicable).
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class RequestMeta(BaseModel, frozen=True):
    """Request-side parameters echoed in every response."""

    mode: Literal["fast", "judge"] | None = None


class ResponseMeta(BaseModel, frozen=True):
    """Response-side metadata in every response.

    ``mode`` may differ from ``RequestMeta.mode`` when judge falls back to fast.
    ``input_hash`` is the HMAC-SHA-256 of the input text (present on detect/pseudonymise/assess).
    ``advisory_disclaimer`` appears only on ``/assess`` responses.
    """

    mode: Literal["fast", "judge"] | None = None
    input_hash: str | None = None
    advisory_disclaimer: str | None = None


class Meta(BaseModel, frozen=True):
    """Envelope metadata wrapping request and response parameters."""

    request: RequestMeta
    response: ResponseMeta


class PriveilResponse(BaseModel, Generic[DataT], frozen=True):
    """Standard response envelope for all Priveil API endpoints."""

    meta: Meta
    data: DataT

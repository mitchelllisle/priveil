"""MCP tool definitions for priveil — detect, anonymise, assess.

Tools are registered on the shared ``mcp`` instance from ``server.py``.
Import this module to trigger registration; it is safe to import multiple times.
"""

from __future__ import annotations

import logging
from typing import Literal, cast

from mcp.server.fastmcp import Context

from priveil.advisor.assessor import ASSESSMENT_ADVISORY_DISCLAIMER
from priveil.advisor.assessor import assess as _llm_assess
from priveil.api.models import Meta, PriveilResponse, RequestMeta, ResponseMeta
from priveil.domain.assessment import AssessmentData, AssessmentRequest
from priveil.domain.detection import DetectionData, DetectionRequest
from priveil.domain.pseudonymisation import OperatorType, PseudonymisationData, PseudonymisationRequest
from priveil.mcp.server import get_state, mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def detect(
    text: str,
    ctx: Context,  # type: ignore[type-arg]  # conduit: FastMCP Context not generic at runtime
    mode: Literal["fast", "advisor"] = "advisor",
) -> PriveilResponse[DetectionData]:
    """Detect PII entities in text.

    Args:
        text: The text to analyse for PII.
        mode: 'advisor' runs an LLM pass to remove false positives (slower, default).
            'fast' returns raw detector output. Falls back to 'fast' when
            PRIVEIL_ADVISOR_MODEL is unset (surfaced via meta.response.mode).

    Returns:
        PriveilResponse with meta (request/response mode and input_hash) and
        data containing the list of detected entities.
    """
    state = get_state(ctx)
    result = await state.analyser.analyse(DetectionRequest(text=text, mode=mode))
    mode_used = mode
    advisor_applied = False
    if mode == "advisor" and state.advisor is not None:
        refined = await state.advisor.advise(text, result.entities)
        result = result.model_copy(update={"entities": refined.entities})
        advisor_applied = refined.advisor_applied
    elif mode == "advisor":
        mode_used = "fast"
        logger.warning(
            "mode='advisor' requested for MCP detect but PRIVEIL_ADVISOR_MODEL is unset; falling back to mode='fast'."
        )
    return PriveilResponse(
        meta=Meta(
            request=RequestMeta(mode=mode),
            response=ResponseMeta(mode=mode_used, input_hash=result.input_hash),
        ),
        data=DetectionData(entities=result.entities, advisor_applied=advisor_applied),
    )


@mcp.tool()
async def anonymise(
    text: str,
    ctx: Context,  # type: ignore[type-arg]  # conduit: FastMCP Context not generic at runtime
    mode: Literal["fast", "advisor"] = "advisor",
    operator_overrides: dict[str, str] | None = None,
) -> PriveilResponse[PseudonymisationData]:
    """Replace detected PII with consistent placeholders.

    Args:
        text: The text to pseudonymise.
        mode: 'fast' or 'advisor' — see detect.
        operator_overrides: Per-entity-type strategy overrides. Keys are entity
            type strings (e.g. 'PERSON', 'AU_TFN'); values are 'replace',
            'mask', 'redact', or 'hash'.

    Returns:
        PriveilResponse with meta and data containing anonymised_text and
        entity_map of original PII spans to replacements.
        The entity_map is sensitive — protect it with the same controls as the
        original text.
    """
    state = get_state(ctx)
    detections = await state.analyser.analyse(DetectionRequest(text=text, mode=mode))
    input_hash = detections.input_hash
    mode_used = mode
    advisor_applied = False
    if mode == "advisor" and state.advisor is not None:
        refined = await state.advisor.advise(text, detections.entities)
        detections = detections.model_copy(update={"entities": refined.entities})
        advisor_applied = refined.advisor_applied
    elif mode == "advisor":
        mode_used = "fast"
        logger.warning(
            "mode='advisor' requested for MCP anonymise but PRIVEIL_ADVISOR_MODEL is unset;"
            " falling back to mode='fast'."
        )
    _VALID_OPERATORS = {"replace", "mask", "redact", "hash"}
    if invalid := {v for v in (operator_overrides or {}).values() if v not in _VALID_OPERATORS}:
        raise ValueError(f"Invalid operator(s): {invalid}. Must be one of {_VALID_OPERATORS}.")
    overrides = {k: cast(OperatorType, v) for k, v in (operator_overrides or {}).items()}
    result = await state.pseudonymiser.pseudonymise(
        PseudonymisationRequest(
            text=text,
            detections=DetectionData(entities=detections.entities),
            operator_overrides=overrides,
            mode="fast",  # refinement already applied above
        )
    )
    return PriveilResponse(
        meta=Meta(
            request=RequestMeta(mode=mode),
            response=ResponseMeta(mode=mode_used, input_hash=input_hash),
        ),
        data=result.model_copy(update={"advisor_applied": advisor_applied}),
    )


@mcp.tool()
async def assess(
    text: str,
    ctx: Context,  # type: ignore[type-arg]  # conduit: FastMCP Context not generic at runtime
    context: str | None = None,
) -> PriveilResponse[AssessmentData]:
    """Assess the sensitivity and regulatory risk of text.

    Args:
        text: The text to assess.
        context: Optional document type or use case description
            (e.g. 'Australian home loan application') to improve accuracy.

    Returns:
        PriveilResponse with meta (input_hash and advisory_disclaimer) and
        data containing sensitivity tier, risk categories, regulatory flags,
        recommended handling, and a per-entity breakdown.
        When laya is installed, sensitivity and categories come from laya typed
        decisions; advisory text is rule-derived (no LLM, no API key required).

    Raises:
        ValueError: If neither laya nor PRIVEIL_ADVISOR_MODEL is configured.
    """
    _LAYA_DISCLAIMER = (
        "Sensitivity and categories derived from laya typed decisions; "
        "regulatory flags and handling guidance are rule-derived, not LLM-generated."
    )
    state = get_state(ctx)
    detections = await state.analyser.analyse(DetectionRequest(text=text))

    # Prefer laya assessor (fast, local, no API key)
    if state.laya_assessor is not None:
        data = await state.laya_assessor.assess(text, detections, context=context)
        return PriveilResponse(
            meta=Meta(
                request=RequestMeta(),
                response=ResponseMeta(
                    input_hash=detections.input_hash,
                    advisory_disclaimer=_LAYA_DISCLAIMER,
                ),
            ),
            data=data,
        )

    # Fall back to LLM assessor
    if state.assessor is not None:
        data = await _llm_assess(AssessmentRequest(text=text, context=context), detections, state.assessor)
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

    raise ValueError(
        "assess requires either laya (uv sync --extra laya) or PRIVEIL_ADVISOR_MODEL to be configured."
    )

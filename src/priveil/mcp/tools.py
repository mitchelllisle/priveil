"""MCP tool definitions for priveil — detect, anonymise, assess.

Tools are registered on the shared ``mcp`` instance from ``server.py``.
Import this module to trigger registration; it is safe to import multiple times.
"""

from __future__ import annotations

import logging
from typing import Literal, cast

from mcp.server.fastmcp import Context

from priveil.api.models import Meta, PriveilResponse, RequestMeta, ResponseMeta
from priveil.domain.assessment import AssessmentData
from priveil.domain.detection import DetectionData, DetectionRequest
from priveil.domain.pseudonymisation import OperatorType, PseudonymisationData, PseudonymisationRequest
from priveil.mcp.server import get_state, mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def detect(
    text: str,
    ctx: Context,  # conduit: FastMCP Context not generic at runtime
    mode: Literal["fast", "judge"] = "judge",
) -> PriveilResponse[DetectionData]:
    """Detect PII entities in text.

    Args:
        text: The text to scan for PII.
        mode: 'fast' runs regex-only; 'judge' additionally runs span
            verification when available. Falls back to 'fast' if laya is not
            installed.

    Returns:
        PriveilResponse with meta (input_hash, mode, judge_applied) and
        data containing a tuple of detected Entity objects.
    """
    state = get_state(ctx)
    result = await state.analyser.analyse(DetectionRequest(text=text, mode=mode))
    mode_used = mode
    judge_applied = False
    if mode == "judge" and state.judge is not None:
        refined = await state.judge.judge(text, result.entities)
        result = result.model_copy(update={"entities": refined.entities})
        judge_applied = refined.judge_applied
    elif mode == "judge":
        mode_used = "fast"
        logger.warning(
            "mode='judge' requested but laya is not installed; falling back to mode='fast'."
        )
    return PriveilResponse(
        meta=Meta(
            request=RequestMeta(mode=mode),
            response=ResponseMeta(
                mode=mode_used,
                input_hash=result.input_hash,
            ),
        ),
        data=DetectionData(entities=result.entities, judge_applied=judge_applied),
    )


@mcp.tool()
async def anonymise(
    text: str,
    ctx: Context,  # conduit: FastMCP Context not generic at runtime
    mode: Literal["fast", "judge"] = "judge",
    operator_overrides: dict[str, str] | None = None,
) -> PriveilResponse[PseudonymisationData]:
    """Replace detected PII with consistent placeholders.

    Args:
        text: The text to pseudonymise.
        mode: 'fast' or 'judge' — see detect.
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
    judge_applied = False
    if mode == "judge" and state.judge is not None:
        refined = await state.judge.judge(text, detections.entities)
        detections = detections.model_copy(update={"entities": refined.entities})
        judge_applied = refined.judge_applied
    elif mode == "judge":
        mode_used = "fast"
        logger.warning(
            "mode='judge' requested for MCP anonymise but laya is not installed;"
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
            mode="fast",  # judge refinement already applied above
        )
    )
    return PriveilResponse(
        meta=Meta(
            request=RequestMeta(mode=mode),
            response=ResponseMeta(mode=mode_used, input_hash=input_hash),
        ),
        data=result.model_copy(update={"judge_applied": judge_applied}),
    )


@mcp.tool()
async def assess(
    text: str,
    ctx: Context,  # conduit: FastMCP Context not generic at runtime
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
        When laya is installed, sensitivity and categories come from judge typed
        decisions; advisory text is rule-derived (no LLM, no API key required).

    Raises:
        ValueError: If laya is not installed.
    """
    _JUDGE_DISCLAIMER = (
        "Sensitivity and categories derived from judge typed decisions; "
        "regulatory flags and handling guidance are rule-derived, not LLM-generated."
    )
    state = get_state(ctx)
    detections = await state.analyser.analyse(DetectionRequest(text=text))

    if state.judge_assessor is not None:
        data = await state.judge_assessor.assess(text, detections, context=context)
        return PriveilResponse(
            meta=Meta(
                request=RequestMeta(),
                response=ResponseMeta(
                    input_hash=detections.input_hash,
                    advisory_disclaimer=_JUDGE_DISCLAIMER,
                ),
            ),
            data=data,
        )

    raise ValueError(
        "assess requires laya (uv sync --extra laya) to be installed."
    )

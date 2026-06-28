"""MCP server exposing priveil's PII tools to LLM clients.

Run as a stdio server:
    uv run python -m priveil.mcp

Then point Claude Desktop / Cursor / any MCP client at this command.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from presidio_anonymizer import AnonymizerEngine

from priveil.domain.assessment import AssessmentRequest
from priveil.domain.detection import DetectionRequest
from priveil.domain.pseudonymisation import OperatorType, PseudonymisationRequest
from priveil.engine.analyser import AsyncAnalyser, build_analyser_engine
from priveil.engine.pseudonymiser import AsyncPseudonymiser
from priveil.judge.refiner import refine as _refine
from priveil.recognisers.registry import build_recognisers
from priveil.settings import Settings


@dataclass
class _State:
    analyser: AsyncAnalyser
    pseudonymiser: AsyncPseudonymiser
    refiner: object | None
    assessor: object | None
    executor: ThreadPoolExecutor


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[_State]:
    settings = Settings()
    executor = ThreadPoolExecutor(max_workers=settings.executor_max_workers)
    engine = build_analyser_engine(
        spacy_model=settings.spacy_model,
        extra_recognisers=build_recognisers(),
    )
    refiner = None
    assessor = None
    if settings.judge_model or settings.judge_base_url:
        from priveil.judge.assessor import build_assessor_agent
        from priveil.judge.refiner import build_refiner_agent

        refiner = build_refiner_agent(settings)
        assessor = build_assessor_agent(settings)

    state = _State(
        analyser=AsyncAnalyser(engine, executor),
        pseudonymiser=AsyncPseudonymiser(AnonymizerEngine(), executor),  # type: ignore[no-untyped-call]
        refiner=refiner,
        assessor=assessor,
        executor=executor,
    )
    try:
        yield state
    finally:
        executor.shutdown(wait=True)


mcp = FastMCP("priveil", lifespan=_lifespan)


def _state(ctx: Context) -> _State:
    return ctx.request_context.lifespan_context  # type: ignore[return-value]


@mcp.tool()
async def detect(
    text: str,
    ctx: Context,
    mode: str = "fast",
) -> dict:  # type: ignore[type-arg]
    """Detect PII entities in text.

    Returns entity types, character offsets, confidence scores, PII classification,
    sensitivity tier, and a SHA-256 audit hash of the input.

    Args:
        text: The text to scan for PII.
        mode: 'fast' returns raw detector output. 'judge' runs an LLM pass to
              remove false positives (requires PRIVEIL_JUDGE_MODEL to be set).
    """
    state = _state(ctx)
    request = DetectionRequest(text=text, mode=mode)
    result = await state.analyser.analyse(request)
    if mode == "judge" and state.refiner is not None:
        result = await _refine(result, text, state.refiner)  # type: ignore[arg-type]
    return result.model_dump()


@mcp.tool()
async def anonymise(
    text: str,
    ctx: Context,
    mode: str = "fast",
    operator_overrides: dict[str, str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Replace detected PII with consistent placeholders.

    Returns the anonymised text and an entity_map recording original PII spans
    for audit purposes. The entity_map is sensitive — treat it with the same
    controls as the original text.

    Args:
        text: The text to pseudonymise.
        mode: 'fast' or 'judge' (see detect).
        operator_overrides: Per-entity-type strategy overrides. Keys are entity
            type strings (e.g. 'PERSON', 'AU_TFN'), values are one of:
            'replace', 'mask', 'redact', 'hash'.
    """
    state = _state(ctx)
    detections = await state.analyser.analyse(DetectionRequest(text=text, mode=mode))
    if mode == "judge" and state.refiner is not None:
        detections = await _refine(detections, text, state.refiner)  # type: ignore[arg-type]
    overrides = {k: OperatorType(v) for k, v in (operator_overrides or {}).items()}
    result = await state.pseudonymiser.pseudonymise(
        PseudonymisationRequest(
            text=text,
            detections=detections,
            operator_overrides=overrides,
            mode="fast",  # refinement already applied above
        )
    )
    return result.model_dump()


@mcp.tool()
async def assess(
    text: str,
    ctx: Context,
    context: str | None = None,
) -> dict:  # type: ignore[type-arg]
    """Assess the sensitivity and regulatory risk of text.

    Returns an overall sensitivity tier (low/medium/high/critical), risk
    categories, applicable Australian regulatory frameworks, recommended
    handling guidance, and a per-entity-type breakdown.

    Requires PRIVEIL_JUDGE_MODEL to be configured.

    Args:
        text: The text to assess.
        context: Optional description of the document type or use case
                 (e.g. 'Australian home loan application') to improve accuracy.
    """
    from priveil.judge.assessor import assess as _assess

    state = _state(ctx)
    if state.assessor is None:
        raise ValueError("assess requires PRIVEIL_JUDGE_MODEL to be configured.")
    detections = await state.analyser.analyse(DetectionRequest(text=text))
    result = await _assess(AssessmentRequest(text=text, context=context), detections, state.assessor)  # type: ignore[arg-type]
    return result.model_dump()


if __name__ == "__main__":
    mcp.run()

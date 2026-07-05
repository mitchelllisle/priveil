"""FastMCP server and lifespan for priveil.

Exposes detect, pseudonymise, and assess as MCP tools backed by the same
engine stack as the FastAPI service.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from presidio_anonymizer import AnonymizerEngine
from pydantic_ai import Agent

from priveil.advisor.assessor import AssessmentDecision
from priveil.advisor.span_advisor import SpanAdvisor
from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser
from priveil.recognisers.registry import build_operator_configs, build_recognisers
from priveil.settings import Settings

try:
    from mcp.server.fastmcp import Context, FastMCP
except ImportError as exc:
    raise ImportError(
        'The priveil MCP server requires the optional "mcp" extra. '
        'Install it with: uv sync --extra mcp'
    ) from exc


@dataclass
class _State:
    analyser: AsyncAnalyser
    pseudonymiser: AsyncPseudonymiser
    advisor: SpanAdvisor | None
    assessor: Agent[None, AssessmentDecision] | None
    executor: ThreadPoolExecutor


logger = logging.getLogger(__name__)



@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[_State]:
    settings = Settings()
    executor = ThreadPoolExecutor(max_workers=settings.executor_max_workers)

    # GLiNER2 model (optional — NER recognisers skipped if not installed)
    gliner_model = None
    try:
        from gliner2 import GLiNER2
        gliner_model = GLiNER2.from_pretrained(settings.gliner2_model)
        logger.info("GLiNER2 model loaded for MCP server.")
    except ImportError:
        logger.warning(
            "gliner2 not installed — NER recognisers disabled. "
            "Install with: uv sync --extra gliner"
        )

    recognisers = build_recognisers(gliner_model=gliner_model)
    audit_hash_key = (
        settings.audit_hash_key.get_secret_value().encode()
        if settings.audit_hash_key
        else None
    )
    analyser = AsyncAnalyser(recognisers, executor, audit_hash_key=audit_hash_key)

    operator_configs = build_operator_configs(recognisers)
    pseudonymiser = AsyncPseudonymiser(
        AnonymizerEngine(),  # type: ignore[no-untyped-call]  # conduit: presidio untyped
        executor, operator_configs=operator_configs
    )

    advisor: SpanAdvisor | None = None
    assessor: Agent[None, AssessmentDecision] | None = None
    if settings.advisor_model:
        from priveil.advisor.assessor import build_assessor_agent
        from priveil.advisor.span_advisor import build_span_advisor

        advisor = build_span_advisor(settings)
        assessor = build_assessor_agent(settings)

    state = _State(
        analyser=analyser,
        pseudonymiser=pseudonymiser,
        advisor=advisor,
        assessor=assessor,
        executor=executor,
    )
    try:
        yield state
    finally:
        executor.shutdown(wait=True)


mcp = FastMCP("priveil", lifespan=_lifespan)


def get_state(ctx: Context) -> _State:  # type: ignore[type-arg]  # conduit: FastMCP Context not generic at runtime
    """Extract typed engine state from the FastMCP request context.

    Args:
        ctx: The FastMCP request context carrying the lifespan state.

    Returns:
        The typed _State dataclass populated during server startup.
    """
    return cast(_State, ctx.request_context.lifespan_context)

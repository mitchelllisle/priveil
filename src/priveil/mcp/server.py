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
from priveil.advisor.laya_assessor import LayaAssessor
from priveil.advisor.span_advisor import AdvisorProtocol
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
    advisor: AdvisorProtocol | None       # SpanAdvisor or LayaSpanAdvisor
    laya_assessor: LayaAssessor | None    # fast assess path (no API key)
    assessor: Agent[None, AssessmentDecision] | None  # LLM assess path
    executor: ThreadPoolExecutor


logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[_State]:
    settings = Settings()
    executor = ThreadPoolExecutor(max_workers=settings.executor_max_workers)

    # ── GLiNER2 model (optional) ───────────────────────────────────────────────
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
    except Exception:
        logger.exception(
            "GLiNER2 model '%s' failed to load — continuing with regex-only detection.",
            settings.gliner2_model,
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
        AnonymizerEngine(),  # type: ignore[no-untyped-call]
        executor, operator_configs=operator_configs
    )

    # ── Span advisor: laya (fast, local) or pydantic-ai LLM ───────────────────
    advisor: AdvisorProtocol | None = None
    ab = settings.advisor_backend
    if ab in ("laya", "auto"):
        try:
            from priveil.advisor.laya_advisor import build_laya_advisor
            advisor = build_laya_advisor(settings, executor)
            logger.info("MCP: laya span advisor active (advisor_backend=%s).", ab)
        except ImportError:
            if ab == "laya":
                logger.error("PRIVEIL_ADVISOR_BACKEND=laya but laya package not installed.")
            else:
                logger.info("MCP: laya not installed; auto falling back to pydantic_ai advisor.")

    if advisor is None and ab != "laya" and settings.advisor_model:
        from priveil.advisor.span_advisor import build_span_advisor
        advisor = build_span_advisor(settings)
        logger.info("MCP: pydantic-ai span advisor active.")

    # ── Assessor: laya (fast, local) or pydantic-ai LLM ──────────────────────
    laya_assessor: LayaAssessor | None = None
    aa = settings.assess_backend
    if aa in ("laya", "auto"):
        try:
            from priveil.advisor.laya_assessor import build_laya_assessor
            laya_assessor = build_laya_assessor(executor, preload=settings.laya_preload)
            logger.info("MCP: laya assessor active (assess_backend=%s).", aa)
        except ImportError:
            if aa == "laya":
                logger.error("PRIVEIL_ASSESS_BACKEND=laya but laya package not installed.")
            else:
                logger.info("MCP: laya not installed; auto falling back to llm assessor.")

    llm_assessor: Agent[None, AssessmentDecision] | None = None
    laya_active = laya_assessor is not None
    if not laya_active and aa != "laya" and settings.advisor_model:
        from priveil.advisor.assessor import build_assessor_agent
        llm_assessor = build_assessor_agent(settings)
        logger.info("MCP: pydantic-ai LLM assessor active.")

    state = _State(
        analyser=analyser,
        pseudonymiser=pseudonymiser,
        advisor=advisor,
        laya_assessor=laya_assessor,
        assessor=llm_assessor,
        executor=executor,
    )
    try:
        yield state
    finally:
        executor.shutdown(wait=True)


mcp = FastMCP("priveil", lifespan=_lifespan)


def get_state(ctx: Context) -> _State:  # type: ignore[type-arg]
    """Extract typed engine state from the FastMCP request context."""
    return cast(_State, ctx.request_context.lifespan_context)

"""FastMCP server and lifespan for priveil.

Import ``mcp`` from this module to mount tools.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from presidio_anonymizer import AnonymizerEngine

from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser
from priveil.judge.assessor import JudgeAssessor
from priveil.judge.judge import JudgeProtocol
from priveil.recognisers.registry import build_operator_configs, build_recognisers
from priveil.settings import Settings

try:
    from mcp.server.fastmcp import Context, FastMCP
except ImportError as exc:
    raise ImportError(
        "mcp package is required for the MCP server. Install with: uv sync --extra mcp"
    ) from exc


@dataclass
class _State:
    analyser: AsyncAnalyser
    pseudonymiser: AsyncPseudonymiser
    judge: JudgeProtocol | None       # SpanJudge or None
    judge_assessor: JudgeAssessor | None    # judge assess path (no API key)
    executor: ThreadPoolExecutor


logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[_State]:
    settings = Settings()
    executor = ThreadPoolExecutor(max_workers=settings.executor_max_workers)

    ner_model = None
    try:
        from gliner2 import GLiNER2
        ner_model = GLiNER2.from_pretrained(settings.ner_model)
        logger.info("NER model loaded for MCP server.")
    except ImportError:
        logger.info(
            "gliner2 not installed — PERSON, LOCATION, DATE_TIME detection disabled. "
            "Install with: uv sync --extra gliner"
        )
    except Exception:
        logger.exception(
            "NER model '%s' failed to load — continuing with regex-only detection.",
            settings.ner_model,
        )

    recognisers = build_recognisers(ner_model=ner_model)
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

    # ── Span judge ────────────────────────────────────────────────────────────
    judge: JudgeProtocol | None = None
    jb = settings.judge_backend
    if jb in ("laya", "auto"):
        try:
            from priveil.judge.judge import build_span_judge
            judge = build_span_judge(settings, executor)
            logger.info("MCP: span judge active (judge_backend=%s).", jb)
        except ImportError:
            if jb == "laya":
                logger.error("PRIVEIL_JUDGE_BACKEND=laya but laya package not installed.")
            else:
                logger.info("MCP: laya not installed; judge mode will fall back to fast.")

    # ── Judge assessor ────────────────────────────────────────────────────────
    judge_assessor: JudgeAssessor | None = None
    aa = settings.assess_backend
    if aa in ("laya", "auto"):
        try:
            from priveil.judge.assessor import build_judge_assessor
            judge_assessor = build_judge_assessor(executor, preload=settings.judge_preload)
            logger.info("MCP: judge assessor active (assess_backend=%s).", aa)
        except ImportError:
            if aa == "laya":
                logger.error("PRIVEIL_ASSESS_BACKEND=laya but laya package not installed.")
            else:
                logger.info("MCP: laya not installed; assess tool will raise if called.")

    state = _State(
        analyser=analyser,
        pseudonymiser=pseudonymiser,
        judge=judge,
        judge_assessor=judge_assessor,
        executor=executor,
    )
    try:
        yield state
    finally:
        executor.shutdown(wait=True)


mcp = FastMCP("priveil", lifespan=_lifespan)


def get_state(ctx: Context) -> _State:
    """Extract typed engine state from the FastMCP request context."""
    return cast(_State, ctx.request_context.lifespan_context)

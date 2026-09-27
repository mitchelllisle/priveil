"""FastMCP server and lifespan for priveil.

Wires up detection, pseudonymisation, span advising (laya), and assessment (laya).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from presidio_anonymizer import AnonymizerEngine

from priveil.advisor.laya_advisor import AdvisorProtocol
from priveil.advisor.laya_assessor import LayaAssessor
from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser
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
    advisor: AdvisorProtocol | None       # LayaSpanAdvisor or None
    laya_assessor: LayaAssessor | None    # fast assess path (no API key)
    executor: ThreadPoolExecutor


logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[_State]:
    settings = Settings()
    executor = ThreadPoolExecutor(max_workers=settings.executor_max_workers)

    recognisers = build_recognisers()
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

    # ── Span advisor: laya (fast, local) ──────────────────────────────────────
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
                logger.info("MCP: laya not installed; advisor mode will fall back to fast.")

    # ── Assessor: laya (fast, local) ──────────────────────────────────────────
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
                logger.info("MCP: laya not installed; assess tool will raise if called.")

    state = _State(
        analyser=analyser,
        pseudonymiser=pseudonymiser,
        advisor=advisor,
        laya_assessor=laya_assessor,
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

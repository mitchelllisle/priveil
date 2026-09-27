from typing import Annotated, cast

from fastapi import Depends, Request
from pydantic_ai import Agent

from priveil.advisor.assessor import AssessmentDecision
from priveil.advisor.laya_assessor import LayaAssessor
from priveil.advisor.span_advisor import AdvisorProtocol
from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser


def _get_analyser(request: Request) -> AsyncAnalyser:
    return cast(AsyncAnalyser, request.app.state.analyser)


AnalyserDep = Annotated[AsyncAnalyser, Depends(_get_analyser)]


def _get_pseudonymiser(request: Request) -> AsyncPseudonymiser:
    return cast(AsyncPseudonymiser, request.app.state.pseudonymiser)


PseudonymiserDep = Annotated[AsyncPseudonymiser, Depends(_get_pseudonymiser)]


def _get_advisor(request: Request) -> AdvisorProtocol | None:
    """Return the active span advisor (SpanAdvisor or LayaSpanAdvisor), or None."""
    return request.app.state.advisor  # type: ignore[no-any-return]  # conduit: app.state untyped


# Optional — routes fall back to fast mode when None.
AdvisorDep = Annotated[AdvisorProtocol | None, Depends(_get_advisor)]


def _get_assessor(request: Request) -> "Agent[None, AssessmentDecision] | None":
    """Return the LLM assessor agent, or None if not configured.

    Routes should check for laya_assessor first (via _get_laya_assessor)
    and only call this for the full LLM assess path.
    """
    return request.app.state.assessor  # type: ignore[no-any-return]


AssessorDep = Annotated["Agent[None, AssessmentDecision] | None", Depends(_get_assessor)]


def _get_laya_assessor(request: Request) -> LayaAssessor | None:
    return getattr(request.app.state, "laya_assessor", None)


# Optional — None when laya is not installed or assess_backend != laya/auto.
LayaAssessorDep = Annotated[LayaAssessor | None, Depends(_get_laya_assessor)]

from typing import Annotated, cast

from fastapi import Depends, Request

from priveil.advisor.laya_advisor import AdvisorProtocol
from priveil.advisor.laya_assessor import LayaAssessor
from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser


def _get_analyser(request: Request) -> AsyncAnalyser:
    return cast(AsyncAnalyser, request.app.state.analyser)


AnalyserDep = Annotated[AsyncAnalyser, Depends(_get_analyser)]


def _get_pseudonymiser(request: Request) -> AsyncPseudonymiser:
    return cast(AsyncPseudonymiser, request.app.state.pseudonymiser)


PseudonymiserDep = Annotated[AsyncPseudonymiser, Depends(_get_pseudonymiser)]


def _get_advisor(request: Request) -> AdvisorProtocol | None:
    """Return the active span advisor (LayaSpanAdvisor), or None."""
    return request.app.state.advisor  # type: ignore[no-any-return]  # conduit: app.state untyped


# Optional — routes fall back to fast mode when None.
AdvisorDep = Annotated[AdvisorProtocol | None, Depends(_get_advisor)]


def _get_laya_assessor(request: Request) -> LayaAssessor | None:
    return getattr(request.app.state, "laya_assessor", None)


# Optional — None when laya is not installed or assess_backend != laya/auto.
LayaAssessorDep = Annotated[LayaAssessor | None, Depends(_get_laya_assessor)]

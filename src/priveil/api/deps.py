from typing import Annotated, cast

from fastapi import Depends, Request

from priveil.judge.judge import JudgeProtocol
from priveil.judge.assessor import JudgeAssessor
from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser


def _get_analyser(request: Request) -> AsyncAnalyser:
    return cast(AsyncAnalyser, request.app.state.analyser)


AnalyserDep = Annotated[AsyncAnalyser, Depends(_get_analyser)]


def _get_pseudonymiser(request: Request) -> AsyncPseudonymiser:
    return cast(AsyncPseudonymiser, request.app.state.pseudonymiser)


PseudonymiserDep = Annotated[AsyncPseudonymiser, Depends(_get_pseudonymiser)]


def _get_judge(request: Request) -> JudgeProtocol | None:
    """Return the active span judge (SpanJudge), or None."""
    return request.app.state.judge  # type: ignore[no-any-return]  # conduit: app.state untyped


# Optional — routes fall back to fast mode when None.
JudgeDep = Annotated[JudgeProtocol | None, Depends(_get_judge)]


def _get_judge_assessor(request: Request) -> JudgeAssessor | None:
    return getattr(request.app.state, "judge_assessor", None)


# Optional — None when laya is not installed or assess_backend != laya/auto.
JudgeAssessorDep = Annotated[JudgeAssessor | None, Depends(_get_judge_assessor)]

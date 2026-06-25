from typing import Annotated

from fastapi import Depends, Request

from alias.engine.analyser import AsyncAnalyser


def _get_analyser(request: Request) -> AsyncAnalyser:
    return request.app.state.analyser  # type: ignore[no-any-return]


AnalyserDep = Annotated[AsyncAnalyser, Depends(_get_analyser)]

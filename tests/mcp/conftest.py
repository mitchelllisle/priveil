"""Fixtures for the MCP tool tests.

engine_state builds real engines (no mocks). The Context is a minimal
SimpleNamespace — just enough to satisfy _state(ctx); no MagicMock needed.
"""

from __future__ import annotations

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest
from presidio_anonymizer import AnonymizerEngine

from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser
from priveil.mcp.server import _State
from priveil.recognisers.registry import build_operator_configs, build_recognisers


@pytest.fixture(scope="session")
def engine_state() -> Generator[_State, None, None]:
    """Real analyser + pseudonymiser, no advisor model.

    Session-scoped so recognisers load once. Executor is shut down on teardown.
    """
    executor = ThreadPoolExecutor(max_workers=2)
    recognisers = build_recognisers()
    operator_configs = build_operator_configs(recognisers)
    state = _State(
        analyser=AsyncAnalyser(recognisers, executor),
        pseudonymiser=AsyncPseudonymiser(AnonymizerEngine(), executor, operator_configs=operator_configs),  # type: ignore[no-untyped-call]
        advisor=None,
        assessor=None,
        executor=executor,
    )
    yield state
    executor.shutdown(wait=True)


def make_ctx(state: _State) -> Any:
    """Minimal context stand-in that satisfies _state(ctx)."""
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=state))

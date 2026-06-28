"""Fixtures for the MCP tool tests.

engine_state builds real engines (no mocks). The Context is a minimal
SimpleNamespace — just enough to satisfy _state(ctx); no MagicMock needed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest
from presidio_anonymizer import AnonymizerEngine

from priveil.engine.analyser import AsyncAnalyser, build_analyser_engine
from priveil.engine.pseudonymiser import AsyncPseudonymiser
from priveil.mcp.server import _State
from priveil.recognisers.registry import build_recognisers


@pytest.fixture(scope="session")
def engine_state() -> _State:
    """Real analyser + pseudonymiser, no judge model."""
    executor = ThreadPoolExecutor(max_workers=2)
    engine = build_analyser_engine(
        spacy_model="en_core_web_sm",
        extra_recognisers=build_recognisers(),
    )
    return _State(
        analyser=AsyncAnalyser(engine, executor),
        pseudonymiser=AsyncPseudonymiser(AnonymizerEngine(), executor),  # type: ignore[no-untyped-call]
        refiner=None,
        assessor=None,
        executor=executor,
    )


def make_ctx(state: _State) -> Any:
    """Minimal context stand-in that satisfies _state(ctx)."""
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=state))

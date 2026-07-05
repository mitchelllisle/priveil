from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from priveil.advisor.assessor import AssessmentDecision
from priveil.advisor.span_advisor import AdvisorResult, SpanAdvisor
from priveil.app import create_app
from priveil.domain.entities import Entity
from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser
from priveil.recognisers.registry import build_operator_configs, build_recognisers
from priveil.settings import Settings


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    # _env_file=None disables .env file loading. OS-level PRIVEIL_* environment
    # variables are still read by BaseSettings — keep them unset in your local
    # shell to avoid polluting the test suite.
    return Settings(_env_file=None)


@pytest.fixture(scope="session")
def analyser() -> Generator[AsyncAnalyser, None, None]:
    """Build the detection engine once per session — regex-only (no GLiNER2 in tests)."""
    executor = ThreadPoolExecutor(max_workers=2)
    recognisers = build_recognisers(gliner_model=None)
    yield AsyncAnalyser(recognisers, executor)
    executor.shutdown(wait=True)


@pytest.fixture(scope="session")
def pseudonymiser() -> Generator[AsyncPseudonymiser, None, None]:
    """Build the AnonymizerEngine once per session."""
    from presidio_anonymizer import AnonymizerEngine

    executor = ThreadPoolExecutor(max_workers=2)
    recognisers = build_recognisers(gliner_model=None)
    operator_configs = build_operator_configs(recognisers)
    yield AsyncPseudonymiser(AnonymizerEngine(), executor, operator_configs=operator_configs)
    executor.shutdown(wait=True)


class _PassThroughAdvisor(SpanAdvisor):
    """Test double that bypasses real LLM calls.

    Uses object.__init__ to avoid requiring a real AsyncOpenAI client and
    Settings, while still satisfying isinstance checks against SpanAdvisor.
    """
    def __init__(self) -> None:
        object.__init__(self)

    async def advise(self, text: str, entities: tuple[Entity, ...]) -> AdvisorResult:
        return AdvisorResult(entities=entities, advisor_applied=True)


@pytest.fixture(scope="session")
def advisor_agent() -> SpanAdvisor:
    """Pass-through advisor for tests that exercise advisor-mode wiring."""
    return _PassThroughAdvisor()


@pytest.fixture(scope="session")
def assessor_agent() -> Agent[None, AssessmentDecision]:
    """TestModel-backed assessor — deterministic, no real LLM calls."""
    return Agent(TestModel(), output_type=AssessmentDecision, system_prompt="test")


# ── Clients ───────────────────────────────────────────────────────────────────


@pytest.fixture
async def client(test_settings: Settings) -> AsyncGenerator[AsyncClient, None]:
    """Baseline client — no engine state injected. Use for health tests."""
    app = create_app(settings=test_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def detect_client(test_settings: Settings, analyser: AsyncAnalyser) -> AsyncGenerator[AsyncClient, None]:
    """Analyser only — no advisor. Tests that advisor mode is silently skipped."""
    app = create_app(settings=test_settings)
    app.state.analyser = analyser
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def pseudonymise_client(
    test_settings: Settings,
    analyser: AsyncAnalyser,
    pseudonymiser: AsyncPseudonymiser,
) -> AsyncGenerator[AsyncClient, None]:
    """Analyser + pseudonymiser, no advisor."""
    app = create_app(settings=test_settings)
    app.state.analyser = analyser
    app.state.pseudonymiser = pseudonymiser
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def advised_client(
    test_settings: Settings,
    analyser: AsyncAnalyser,
    pseudonymiser: AsyncPseudonymiser,
    advisor_agent: SpanAdvisor,
) -> AsyncGenerator[AsyncClient, None]:
    """Analyser + pseudonymiser + pass-through advisor — tests the advisor path."""
    app = create_app(settings=test_settings)
    app.state.analyser = analyser
    app.state.pseudonymiser = pseudonymiser
    app.state.advisor = advisor_agent
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def assess_client(
    test_settings: Settings,
    analyser: AsyncAnalyser,
    assessor_agent: Agent[None, AssessmentDecision],
) -> AsyncGenerator[AsyncClient, None]:
    """Analyser + TestModel assessor — for /assess endpoint tests."""
    app = create_app(settings=test_settings)
    app.state.analyser = analyser
    app.state.assessor = assessor_agent
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

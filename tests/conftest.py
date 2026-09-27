from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from priveil.advisor.laya_advisor import AdvisorProtocol, AdvisorResult
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
    recognisers = build_recognisers()
    yield AsyncAnalyser(recognisers, executor)
    executor.shutdown(wait=True)


@pytest.fixture(scope="session")
def pseudonymiser() -> Generator[AsyncPseudonymiser, None, None]:
    """Build the AnonymizerEngine once per session."""
    from presidio_anonymizer import AnonymizerEngine

    executor = ThreadPoolExecutor(max_workers=2)
    recognisers = build_recognisers()
    operator_configs = build_operator_configs(recognisers)
    yield AsyncPseudonymiser(AnonymizerEngine(), executor, operator_configs=operator_configs)
    executor.shutdown(wait=True)


@pytest.fixture(scope="session")
def advisor_mock() -> AdvisorProtocol:
    """Pass-through advisor mock — satisfies AdvisorProtocol, applies no real verification."""
    async def _advise(text: str, entities: tuple[Entity, ...]) -> AdvisorResult:
        return AdvisorResult(entities=entities, advisor_applied=True)

    mock = MagicMock(spec=AdvisorProtocol)
    mock.advise = AsyncMock(side_effect=_advise)
    return mock  # type: ignore[return-value]


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
    advisor_mock: AdvisorProtocol,
) -> AsyncGenerator[AsyncClient, None]:
    """Analyser + pseudonymiser + pass-through advisor — tests the advisor path."""
    app = create_app(settings=test_settings)
    app.state.analyser = analyser
    app.state.pseudonymiser = pseudonymiser
    app.state.advisor = advisor_mock
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def laya_assess_client(
    test_settings: Settings,
    analyser: AsyncAnalyser,
) -> AsyncGenerator[AsyncClient, None]:
    """Analyser + mock LayaAssessor — tests the laya-first dispatch path."""
    from concurrent.futures import ThreadPoolExecutor

    from priveil.advisor.laya_assessor import LayaAssessor

    router = MagicMock()
    router.predict.return_value = {
        "answers": {
            "overall_sensitivity": {"choice": "medium"},
            "is_financial": {"noul": 0.8},
            "is_identity": {"noul": 0.3},
            "is_medical": {"noul": 0.1},
            "is_employment": {"noul": 0.1},
        }
    }
    executor = ThreadPoolExecutor(max_workers=1)
    laya_assessor = LayaAssessor(router=router, executor=executor)

    app = create_app(settings=test_settings)
    app.state.analyser = analyser
    app.state.laya_assessor = laya_assessor
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    executor.shutdown(wait=False)

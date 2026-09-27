import importlib.metadata
import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from presidio_anonymizer import AnonymizerEngine

from priveil.api.routes import assess, detect, health, pseudonymise
from priveil.domain.detection import DetectionRequest
from priveil.engine.analyser import AsyncAnalyser
from priveil.engine.pseudonymiser import AsyncPseudonymiser
from priveil.recognisers.registry import build_operator_configs, build_recognisers
from priveil.settings import Settings

logger = logging.getLogger(__name__)


def _version() -> str:
    """Return the package version, falling back to 'dev' for source checkouts."""
    try:
        return importlib.metadata.version("priveil")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hook — initialise engines, yield, then clean up."""
    settings: Settings = app.state.settings
    executor = ThreadPoolExecutor(max_workers=settings.executor_max_workers)

    # ── Detection engine ──────────────────────────────────────────────────────
    recognisers = build_recognisers()
    audit_hash_key = settings.audit_hash_key.get_secret_value().encode() if settings.audit_hash_key else None
    if audit_hash_key is None:
        logger.warning(
            "PRIVEIL_AUDIT_HASH_KEY is unset; using an ephemeral process-local audit hash key. "
            "Set PRIVEIL_AUDIT_HASH_KEY to keep hashes stable across restarts."
        )
    if getattr(app.state, "analyser", None) is None:
        app.state.analyser = AsyncAnalyser(recognisers, executor, audit_hash_key=audit_hash_key)

    # ── Pseudonymiser — operator configs from recognisers ─────────────────────
    if getattr(app.state, "pseudonymiser", None) is None:
        operator_configs = build_operator_configs(recognisers)
        app.state.pseudonymiser = AsyncPseudonymiser(
            AnonymizerEngine(),  # type: ignore[no-untyped-call]  # conduit: presidio untyped
            executor, operator_configs=operator_configs
        )

    # ── Span advisor (Laya) ───────────────────────────────────────────────────
    if getattr(app.state, "advisor", None) is None:
        backend = settings.advisor_backend
        if backend in ("laya", "auto"):
            try:
                from priveil.advisor.laya_advisor import build_laya_advisor

                app.state.advisor = build_laya_advisor(settings, executor)
                logger.info("Laya span advisor active (backend=%s).", backend)
            except ImportError:
                if backend == "laya":
                    logger.error(
                        "PRIVEIL_ADVISOR_BACKEND=laya but laya package is not installed. "
                        "Install with: uv sync --extra laya"
                    )
                else:
                    logger.info(
                        "No advisor configured (laya not installed); "
                        "mode='advisor' falls back to 'fast'. "
                        "Install laya (uv sync --extra laya) to enable zero-config span advisor."
                    )
                app.state.advisor = None

        # ── Assessor: Laya ────────────────────────────────────────────────────
        ab = settings.assess_backend
        if getattr(app.state, "laya_assessor", None) is None and ab in ("laya", "auto"):
            try:
                from priveil.advisor.laya_assessor import build_laya_assessor

                app.state.laya_assessor = build_laya_assessor(executor, preload=settings.laya_preload)
                logger.info("Laya assessor active (assess_backend=%s).", ab)
            except ImportError:
                if ab == "laya":
                    logger.error(
                        "PRIVEIL_ASSESS_BACKEND=laya but laya package is not installed. "
                        "Install with: uv sync --extra laya"
                    )
                else:
                    logger.info("laya not installed; /assess will return 503 when called.")
                app.state.laya_assessor = None

    # ── Warmup ────────────────────────────────────────────────────────────────
    await app.state.analyser.analyse(DetectionRequest(text="Warmup: TFN 123 456 782", mode="fast"))
    if app.state.advisor is not None:
        with suppress(Exception):
            warmup = await app.state.analyser.analyse(DetectionRequest(text="Warmup TFN 123 456 782", mode="fast"))
            await app.state.advisor.advise("Warmup TFN 123 456 782", warmup.entities)

    yield
    executor.shutdown(wait=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return the configured FastAPI application.

    Args:
        settings: Optional override; defaults to env-driven Settings().

    Returns:
        A fully configured FastAPI app.
    """
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="Priveil",
        description="Pseudonymisation service for reducing PII exposure in text workflows.",
        version=_version(),
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Initialise all engine state to None so tests that bypass the lifespan
    # never hit AttributeError on app.state.<key>.
    app.state.analyser = None
    app.state.pseudonymiser = None
    app.state.advisor = None
    app.state.laya_assessor = None

    app.include_router(health.router)
    app.include_router(detect.router, prefix="/detect", tags=["detection"])
    app.include_router(pseudonymise.router, prefix="/pseudonymise", tags=["pseudonymisation"])
    app.include_router(assess.router, prefix="/assess", tags=["assessment"])

    return app


app = create_app()

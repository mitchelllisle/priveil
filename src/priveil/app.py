import importlib.metadata
import logging
from collections.abc import AsyncGenerator
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
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup / shutdown hook — initialise engines, yield, then clean up."""
    settings: Settings = app.state.settings
    executor = ThreadPoolExecutor(max_workers=settings.executor_max_workers)

    # ── NER model (optional — NER recognisers skipped if not installed) ────────
    ner_model = None
    try:
        from gliner2 import GLiNER2
        logger.info("Loading NER model '%s'…", settings.ner_model)
        ner_model = GLiNER2.from_pretrained(settings.ner_model)
        logger.info("NER model loaded — PERSON, LOCATION, DATE_OF_BIRTH active.")
    except ImportError:
        logger.info(
            "gliner2 not installed — PERSON, LOCATION, DATE_OF_BIRTH detection disabled. "
            "Install with: uv sync --extra gliner"
        )
    except Exception:
        logger.exception(
            "NER model '%s' failed to load — continuing with regex-only detection.",
            settings.ner_model,
        )

    # ── Detection engine ──────────────────────────────────────────────────────
    recognisers = build_recognisers(ner_model=ner_model)
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

    # ── Span judge ────────────────────────────────────────────────────────────
    if getattr(app.state, "judge", None) is None:
        backend = settings.judge_backend
        if backend in ("laya", "auto"):
            try:
                from priveil.judge.judge import build_span_judge

                app.state.judge = build_span_judge(settings, executor)
                logger.info("Span judge active (backend=%s).", backend)
            except ImportError:
                logger.info(
                    "laya not installed; mode='judge' falls back to 'fast'. "
                    "Install with: uv sync --extra laya"
                ) if backend != "laya" else logger.error(
                    "PRIVEIL_JUDGE_BACKEND=laya but laya package is not installed."
                )
                app.state.judge = None

    # ── Judge assessor — independent of span judge ────────────────────────────
    if getattr(app.state, "judge_assessor", None) is None:
        ab = settings.assess_backend
        if ab in ("laya", "auto"):
            try:
                from priveil.judge.assessor import build_judge_assessor

                app.state.judge_assessor = build_judge_assessor(executor, preload=settings.judge_preload)
                logger.info("Judge assessor active (assess_backend=%s).", ab)
            except ImportError:
                logger.info(
                    "laya not installed; /assess will return 503 when called."
                ) if ab != "laya" else logger.error(
                    "PRIVEIL_ASSESS_BACKEND=laya but laya package is not installed."
                )
                app.state.judge_assessor = None

    # ── Warmup ────────────────────────────────────────────────────────────────
    await app.state.analyser.analyse(DetectionRequest(text="Warmup: TFN 123 456 782", mode="fast"))
    if app.state.judge is not None:
        with suppress(Exception):
            warmup = await app.state.analyser.analyse(DetectionRequest(text="Warmup TFN 123 456 782", mode="fast"))
            await app.state.judge.judge("Warmup TFN 123 456 782", warmup.entities)

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
    app.state.judge = None
    app.state.judge_assessor = None

    app.include_router(health.router)
    app.include_router(detect.router, prefix="/detect", tags=["detection"])
    app.include_router(pseudonymise.router, prefix="/pseudonymise", tags=["pseudonymisation"])
    app.include_router(assess.router, prefix="/assess", tags=["assessment"])

    return app


app = create_app()

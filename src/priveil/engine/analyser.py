import asyncio
import secrets
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache, partial
from typing import Literal

from presidio_analyzer import AnalyzerEngine, EntityRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.recognizer_result import RecognizerResult

from priveil.domain.detection import DetectionData, DetectionRequest, DetectionResult
from priveil.domain.entities import ENTITY_CLASSIFICATION, Entity, EntityType


@lru_cache(maxsize=1)
def _ephemeral_audit_key() -> bytes:
    """Return a process-scoped ephemeral HMAC key for audit hashing.

    lru_cache ensures every ``AsyncAnalyser`` instance without an explicit key
    shares the same bytes object for the process lifetime. Hashes are therefore
    stable across requests even if the analyser is reconstructed.
    """
    return secrets.token_bytes(32)


def build_analyser_engine(
    spacy_model: str,
    extra_recognisers: list[EntityRecognizer] | None = None,
) -> AnalyzerEngine:
    """Build and configure a presidio AnalyzerEngine.

    Args:
        spacy_model: spaCy model name to use for NLP processing.
        extra_recognisers: Additional recognisers to register.

    Returns:
        Configured AnalyzerEngine with all recognisers registered.
    """
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": spacy_model}],
        }
    )
    nlp_engine = provider.create_engine()
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    for recogniser in extra_recognisers or []:
        registry.add_recognizer(recogniser)
    return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry)


def _to_entity(result: RecognizerResult, text: str) -> Entity | None:
    """Convert a presidio RecognizerResult to an Entity.

    Args:
        result: Presidio recognition result with entity type and offsets.
        text: Original text the result was extracted from.

    Returns:
        Entity if the entity type is known, None otherwise.
    """
    try:
        entity_type = EntityType(result.entity_type)
    except ValueError:
        return None
    is_pii, sensitivity = ENTITY_CLASSIFICATION[entity_type]
    return Entity(
        text=text[result.start : result.end],
        entity_type=entity_type,
        start=result.start,
        end=result.end,
        score=round(result.score, 4),
        is_pii=is_pii,
        sensitivity=sensitivity,
    )


class AsyncAnalyser:
    """Async wrapper around presidio AnalyzerEngine.

    Offloads CPU-bound analysis to a thread-pool executor so it does not block
    the event loop.
    """

    def __init__(
        self,
        engine: AnalyzerEngine,
        executor: ThreadPoolExecutor,
        audit_hash_key: bytes | None = None,
    ) -> None:
        self._engine = engine
        self._executor = executor
        # Use the caller-supplied key (for stable cross-restart correlation) or
        # fall back to a process-scoped ephemeral key (consistent within a process
        # lifetime even if the analyser is reconstructed).
        self._audit_hash_key = audit_hash_key if audit_hash_key is not None else _ephemeral_audit_key()

    async def analyse(self, request: DetectionRequest) -> DetectionResult:
        """Detect PII entities in text.

        Args:
            request: DetectionRequest with text and language code.

        Returns:
            DetectionResult with all recognised entities and an audit hash.
        """
        loop = asyncio.get_running_loop()
        _run = partial(
            self._engine.analyze,
            text=request.text,
            language=request.language,
            return_decision_process=False,
        )
        results = await loop.run_in_executor(self._executor, _run)
        entities = [e for r in results if (e := _to_entity(r, request.text)) is not None]
        return DetectionResult.from_text(
            text=request.text,
            entities=entities,
            mode_requested=request.mode,
            mode_used=request.mode,
            hash_key=self._audit_hash_key,
        )

    def detections_from_entities(
        self,
        text: str,
        entities: tuple[Entity, ...],
        mode: Literal["fast", "judge"] = "fast",
    ) -> DetectionResult:
        """Build an internal DetectionResult from pre-computed DetectionData entities.

        Used by routes when a client passes pre-computed ``DetectionData`` so that
        the refiner pipeline receives a full ``DetectionResult`` (with stable hash).

        Args:
            text: The original input text (used to compute the audit hash).
            entities: Entities from the pre-computed ``DetectionData``.
            mode: Mode to record on the result.

        Returns:
            DetectionResult with the engine's stable audit hash key applied.
        """
        return DetectionResult.from_text(
            text=text,
            entities=list(entities),
            mode_requested=mode,
            mode_used=mode,
            hash_key=self._audit_hash_key,
        )

    def to_detection_data(self, result: DetectionResult) -> DetectionData:
        """Project an internal DetectionResult to the API-visible DetectionData."""
        return DetectionData(entities=result.entities)

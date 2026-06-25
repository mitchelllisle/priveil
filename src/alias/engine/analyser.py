import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from presidio_analyzer import AnalyzerEngine, EntityRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.recognizer_result import RecognizerResult

from alias.domain.detection import DetectionRequest, DetectionResult
from alias.domain.entities import ENTITY_CLASSIFICATION, Entity, EntityType


def build_analyser_engine(
    spacy_model: str,
    extra_recognisers: list[EntityRecognizer] | None = None,
) -> AnalyzerEngine:
    """Build and configure a presidio AnalyzerEngine.

    Args:
        spacy_model: spaCy model name, e.g. 'en_core_web_lg'.
        extra_recognisers: Additional recognisers to register (added in later slices).

    Returns:
        A fully configured AnalyzerEngine ready for analysis.
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

    Presidio results cross a trust boundary — unknown entity types are filtered
    rather than passed through, so the rest of the system only sees types
    explicitly declared in EntityType.

    Args:
        result: Raw result from presidio AnalyzerEngine.
        text: The original input text (used to extract the matched span).

    Returns:
        Entity if the type is in EntityType, None otherwise.
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

    presidio is synchronous; every call is offloaded to a thread-pool executor
    so the event loop is never blocked.
    """

    def __init__(self, engine: AnalyzerEngine, executor: ThreadPoolExecutor) -> None:
        self._engine = engine
        self._executor = executor

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
        return DetectionResult.from_text(text=request.text, entities=entities)

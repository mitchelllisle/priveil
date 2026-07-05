"""Detection engine — runs all registered recognisers and returns Entity spans.

Replaces the previous Presidio + spaCy pipeline.  Detection is now driven
entirely by ``BaseRecogniser`` subclasses:

- ``RegexRecogniser``   — pattern matching + optional checksum (AU_TFN, email, …)
- ``GLiNERRecogniser``  — GLiNER2-powered NER (PERSON, LOCATION, DATE_TIME, …)

All recognisers run concurrently in a shared thread-pool executor (CPU-bound).
Overlapping spans from different recognisers are deduplicated by keeping the
highest-score span.  Each entity carries the recogniser's ``verification``
declaration (``"trust"`` or ``"advisor"``) so the SpanAdvisor can route
without a separate settings lookup.
"""

from __future__ import annotations

import asyncio
import secrets
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Literal

from priveil.domain.detection import DetectionData, DetectionRequest, DetectionResult
from priveil.domain.entities import Entity
from priveil.recognisers.base import BaseRecogniser, Span


@lru_cache(maxsize=1)
def _ephemeral_audit_key() -> bytes:
    """Return a process-scoped ephemeral HMAC key for audit hashing.

    ``lru_cache`` ensures a single key per process lifetime even if the
    engine is reconstructed.
    """
    return secrets.token_bytes(32)


def _dedup_global(tagged: list[tuple[Span, BaseRecogniser]]) -> list[tuple[Span, BaseRecogniser]]:
    """Remove overlapping spans across all recognisers, keeping the highest score.

    Args:
        tagged: Unsorted list of (span, recogniser) pairs.

    Returns:
        Non-overlapping list sorted by start offset.
    """
    if not tagged:
        return []
    sorted_tagged = sorted(tagged, key=lambda x: (x[0].start, -x[0].score))
    result: list[tuple[Span, BaseRecogniser]] = [sorted_tagged[0]]
    for span, rec in sorted_tagged[1:]:
        prev_span, _ = result[-1]
        if span.start < prev_span.end:
            # Overlap — keep whichever has higher score
            if span.score > prev_span.score:
                result[-1] = (span, rec)
        else:
            result.append((span, rec))
    return result


def _to_entity(span: Span, recogniser: BaseRecogniser) -> Entity:
    return Entity(
        text=span.text,
        entity_type=recogniser.entity_type,
        start=span.start,
        end=span.end,
        score=span.score,
        is_pii=recogniser.is_pii,
        sensitivity=recogniser.sensitivity,
        verification=recogniser.verification,
    )


class AsyncAnalyser:
    """Async wrapper around the recogniser stack.

    Offloads CPU-bound detection to a thread-pool executor so it never blocks
    the event loop.  The public interface is intentionally identical to the
    previous Presidio-based ``AsyncAnalyser`` so routes and deps need no changes.
    """

    def __init__(
        self,
        recognisers: list[BaseRecogniser],
        executor: ThreadPoolExecutor,
        audit_hash_key: bytes | None = None,
    ) -> None:
        self._recognisers = recognisers
        self._executor = executor
        self._audit_hash_key = audit_hash_key if audit_hash_key is not None else _ephemeral_audit_key()

    async def analyse(self, request: DetectionRequest) -> DetectionResult:
        """Detect PII entities in text.

        Runs all recognisers concurrently, deduplicates overlapping spans, and
        returns a ``DetectionResult`` with a stable HMAC audit hash.
        """
        loop = asyncio.get_running_loop()
        futures = [
            loop.run_in_executor(self._executor, r.detect, request.text)
            for r in self._recognisers
        ]
        all_results: list[list[Span]] = list(await asyncio.gather(*futures))

        tagged: list[tuple[Span, BaseRecogniser]] = []
        for recogniser, spans in zip(self._recognisers, all_results):
            for span in spans:
                tagged.append((span, recogniser))

        deduped = _dedup_global(tagged)
        entities = [_to_entity(span, rec) for span, rec in deduped]

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
        mode: Literal["fast", "advisor"] = "fast",
    ) -> DetectionResult:
        """Build a DetectionResult from pre-computed entities (e.g. from a prior /detect call)."""
        return DetectionResult.from_text(
            text=text,
            entities=list(entities),
            mode_requested=mode,
            mode_used=mode,
            hash_key=self._audit_hash_key,
        )

    def to_detection_data(self, result: DetectionResult) -> DetectionData:
        return DetectionData(entities=result.entities)

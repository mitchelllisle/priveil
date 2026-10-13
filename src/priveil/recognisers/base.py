"""Base classes for the Priveil recogniser stack.

Four public classes are exported:
- Span          — a detected text span with position and score
- BaseRecogniser — abstract interface every recogniser implements
- RegexRecogniser — base for pattern-based recognisers with optional validation
- NERRecogniser — base for NER model-powered recognisers
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal, NamedTuple

from priveil.domain.entities import EntityType, Sensitivity


class Span(NamedTuple):
    """A detected entity span."""

    text: str
    start: int
    end: int
    score: float


class BaseRecogniser(ABC):
    """Abstract base for all entity recognisers.

    Each concrete recogniser owns its entity type, PII classification,
    sensitivity, verification strategy, and default pseudonymisation operator.
    """

    entity_type: ClassVar[EntityType]
    is_pii: ClassVar[bool]
    sensitivity: ClassVar[Sensitivity]
    verification: ClassVar[Literal["trust", "judge"]]
    default_operator: ClassVar[str]          # "replace" | "mask" | "redact" | "hash"
    default_operator_params: ClassVar[dict[str, object]]
    # Higher priority wins when spans overlap. Deterministic (regex/checksum)
    # recognisers take priority over probabilistic NER models.
    priority: ClassVar[int] = 0

    @abstractmethod
    def detect(self, text: str) -> list[Span]:
        """Return all detected spans for this recogniser's entity type."""
        ...


class RegexRecogniser(BaseRecogniser, ABC):
    """Base for pattern-driven recognisers with optional context boosting and validation.

    Subclasses declare:
    - ``patterns``: one or more compiled regex patterns to scan.
    - ``context_words``: lower-case words/phrases that indicate the entity type;
      finding any of them within 100 characters of a match boosts the score.
    - ``_validate(text)``: optional hook for checksum or format validation.
      Return ``False`` to discard the span; ``True`` or ``None`` to keep it.
    """

    patterns: ClassVar[list[re.Pattern[str]]]
    context_words: ClassVar[list[str]] = []
    priority: ClassVar[int] = 1  # beats NERRecogniser (0) on overlapping spans

    _BASE_SCORE: ClassVar[float] = 0.8
    _CONTEXT_BOOST: ClassVar[float] = 0.15
    _CONTEXT_WINDOW: ClassVar[int] = 100

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        text_lower = text.lower()

        for pattern in self.patterns:
            for match in pattern.finditer(text):
                matched_text = match.group()

                if self._validate(matched_text) is False:
                    continue

                score = self._BASE_SCORE

                # Context boost: search a window of ±_CONTEXT_WINDOW chars around the match.
                window_start = max(0, match.start() - self._CONTEXT_WINDOW)
                window_end = min(len(text), match.end() + self._CONTEXT_WINDOW)
                window = text_lower[window_start:window_end]

                if any(re.search(r"\b" + re.escape(cw) + r"\b", window) for cw in self.context_words):
                    score = min(1.0, score + self._CONTEXT_BOOST)

                spans.append(Span(
                    text=matched_text,
                    start=match.start(),
                    end=match.end(),
                    score=score,
                ))

        # Deduplicate: multiple patterns may produce the same span; keep highest score.
        seen: dict[tuple[int, int], Span] = {}
        for span in spans:
            key = (span.start, span.end)
            if key not in seen or span.score > seen[key].score:
                seen[key] = span

        return sorted(seen.values(), key=lambda s: s.start)

    def _validate(self, text: str) -> bool | None:
        """Optional validation hook.

        Returns:
            False  — span is invalid; discard it.
            True   — span is valid.
            None   — no opinion; span is kept at its current score.
        """
        return None


def _dedup_overlapping(spans: list[Span]) -> list[Span]:
    """Remove overlapping spans from a start-sorted list, keeping the highest score."""
    result: list[Span] = []
    for span in spans:
        if not result:
            result.append(span)
            continue
        prev = result[-1]
        if span.start < prev.end:  # Overlapping
            if span.score > prev.score:
                result[-1] = span
            # else: keep prev, discard span
        else:
            result.append(span)
    return result


class NERRecogniser(BaseRecogniser, ABC):
    """Base for NER model-powered recognisers.

    Subclasses declare:
    - ``ner_labels``: mapping of NER label key → human description fed to the model.
    - ``ner_threshold``: minimum confidence score for a detection to be kept.

    The constructor receives the shared NER model instance.
    """

    ner_labels: ClassVar[dict[str, str]]
    ner_threshold: ClassVar[float] = 0.5
    min_span_chars: ClassVar[int] = 0
    denylist: ClassVar[frozenset[str]] = frozenset()
    # Neural models return overconfident scores (1.0) even for FPs. Cap score
    # below judge_score_threshold (default 0.9) so every verification="judge"
    # NER entity always reaches laya rather than being bypassed as "certain".
    max_score: ClassVar[float] = 0.89

    def __init__(self, model: Any) -> None:  # conduit: Any — NER model ships no stubs at runtime
        self._model = model

    def detect(self, text: str) -> list[Span]:
        result = self._model.extract_entities(
            text,
            list(self.ner_labels.keys()),
            threshold=self.ner_threshold,
            include_confidence=True,
            include_spans=True,
        )

        spans: list[Span] = []
        entities_by_label: dict[str, list[dict[str, Any]]] = result.get("entities", {})

        for label_key in self.ner_labels:
            for e in entities_by_label.get(label_key, []):
                conf: float = e.get("confidence", 0.8)
                if conf < self.ner_threshold:
                    continue
                if (e["end"] - e["start"]) < self.min_span_chars:
                    continue
                if e["text"].lower() in self.denylist:
                    continue
                spans.append(Span(
                    text=e["text"],
                    start=e["start"],
                    end=e["end"],
                    score=min(conf, self.max_score),
                ))

        spans.sort(key=lambda s: s.start)
        return _dedup_overlapping(spans)

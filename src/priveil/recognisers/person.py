"""Person name recogniser backed by GLiNER2."""

from __future__ import annotations

from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import GLiNERRecogniser


class PersonRecogniser(GLiNERRecogniser):
    """Detect full names of real persons using GLiNER2.

    min_span_chars=3: drops single-char initials and two-letter tokens.
    denylist: common English pronouns and honorifics that GLiNER2 sometimes
    misidentifies as named persons.
    """

    entity_type: ClassVar[EntityType] = EntityType.PERSON
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "high"
    verification: ClassVar[Literal["trust", "judge"]] = "judge"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<PERSON>"}

    gliner_labels: ClassVar[dict[str, str]] = {
        "person": "Full name of a real person or individual",
    }
    gliner_threshold: ClassVar[float] = 0.5
    min_span_chars: ClassVar[int] = 3
    denylist: ClassVar[frozenset[str]] = frozenset({
        # personal pronouns
        "i", "me", "my", "myself",
        "you", "your", "yourself",
        "he", "him", "his", "himself",
        "she", "her", "hers", "herself",
        "it", "its", "itself",
        "we", "us", "our", "ourselves",
        "they", "them", "their", "theirs", "themselves",
        # demonstratives / relative that get caught
        "who", "whom", "this", "that",
    })

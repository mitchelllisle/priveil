"""Geographic location recogniser backed by GLiNER2."""

from __future__ import annotations

from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import GLiNERRecogniser


class LocationRecogniser(GLiNERRecogniser):
    """Detect physical addresses, suburbs, cities, and geographic places using GLiNER2.

    threshold=0.7: eliminates low-confidence location guesses on financial codes.
    min_span_chars=5: drops 3-letter acronyms (TFN, ABN, BSB) that GLiNER2
    confuses for place abbreviations.
    """

    entity_type: ClassVar[EntityType] = EntityType.LOCATION
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "low"
    verification: ClassVar[Literal["trust", "judge"]] = "judge"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<LOCATION>"}

    gliner_labels: ClassVar[dict[str, str]] = {
        "location": "Physical address, suburb, city, or geographic place",
    }
    gliner_threshold: ClassVar[float] = 0.7
    min_span_chars: ClassVar[int] = 5

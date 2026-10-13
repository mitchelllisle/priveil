"""Geographic location recogniser backed by a NER model."""

from __future__ import annotations

from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import NERRecogniser


class LocationRecogniser(NERRecogniser):
    """Detect physical addresses, suburbs, cities, and geographic places using a NER model.

    threshold=0.7: eliminates low-confidence location guesses on financial codes.
    min_span_chars=5: drops 3-letter acronyms (TFN, ABN, BSB) that the NER model
    confuses for place abbreviations.
    """

    entity_type: ClassVar[EntityType] = EntityType.LOCATION
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "low"
    verification: ClassVar[Literal["trust", "judge"]] = "judge"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<LOCATION>"}

    ner_labels: ClassVar[dict[str, str]] = {
        "location": "Physical address, suburb, city, or geographic place",
    }
    ner_threshold: ClassVar[float] = 0.7
    min_span_chars: ClassVar[int] = 5

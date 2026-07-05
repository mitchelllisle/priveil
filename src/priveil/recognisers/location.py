"""Geographic location recogniser backed by GLiNER2."""

from __future__ import annotations

from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import GLiNERRecogniser


class LocationRecogniser(GLiNERRecogniser):
    """Detect physical addresses, suburbs, cities, and geographic places using GLiNER2."""

    entity_type: ClassVar[EntityType] = EntityType.LOCATION
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "low"
    verification: ClassVar[Literal["trust", "advisor"]] = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<LOCATION>"}

    gliner_labels: ClassVar[dict[str, str]] = {
        "location": "Physical address, suburb, city, or geographic place",
    }
    gliner_threshold: ClassVar[float] = 0.5

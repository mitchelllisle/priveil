"""Person name recogniser backed by GLiNER2."""

from __future__ import annotations

from typing import ClassVar

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import GLiNERRecogniser


class PersonRecogniser(GLiNERRecogniser):
    """Detect full names of real persons using GLiNER2."""

    entity_type: ClassVar[EntityType] = EntityType.PERSON
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "high"
    verification: ClassVar = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<PERSON>"}

    gliner_labels: ClassVar[dict[str, str]] = {
        "person": "Full name of a real person or individual",
    }
    gliner_threshold: ClassVar[float] = 0.5

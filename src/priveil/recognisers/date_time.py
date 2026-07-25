"""Date and time reference recogniser backed by GLiNER2."""

from __future__ import annotations

from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import GLiNERRecogniser


class DateTimeRecogniser(GLiNERRecogniser):
    """Detect specific dates, times, or temporal references using GLiNER2.

    Not classified as PII on its own; verification is delegated to advisor because
    temporal references often need context to determine whether they identify a person.
    Lower threshold (0.3) to err toward recall given the advisory workflow.
    """

    entity_type: ClassVar[EntityType] = EntityType.DATE_TIME
    is_pii: ClassVar[bool] = False
    sensitivity: ClassVar[Sensitivity] = "low"
    verification: ClassVar[Literal["trust", "advisor"]] = "advisor"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<DATE>"}

    gliner_labels: ClassVar[dict[str, str]] = {
        "date": "Specific date, time, or temporal reference that could identify a person",
    }
    gliner_threshold: ClassVar[float] = 0.3

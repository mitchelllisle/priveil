"""Date of birth recogniser backed by a NER model."""

from __future__ import annotations

from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import NERRecogniser


class DateOfBirthRecogniser(NERRecogniser):
    """Detect dates of birth using a NER model.

    Targets personal birth dates only — the label is specific enough that
    scheduling dates ("let's meet on the 2nd") are not detected. Typical
    cases caught: "DOB: 12/06/1990", "born on 14 March 1985", "my birthday
    is 2nd October 1967".
    """

    entity_type: ClassVar[EntityType] = EntityType.DATE_OF_BIRTH
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "high"
    verification: ClassVar[Literal["trust", "judge"]] = "judge"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<DOB>"}

    ner_labels: ClassVar[dict[str, str]] = {
        "date_of_birth": "A person's date of birth or personal birth date",
    }
    ner_threshold: ClassVar[float] = 0.5

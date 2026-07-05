"""Australian mobile and landline phone number recogniser."""

from __future__ import annotations

import re
from typing import ClassVar

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser


class AUPhoneRecogniser(RegexRecogniser):
    """Detect Australian mobile and landline phone numbers.

    Patterns:
    - Mobile: 04XX format, local or with +61 country code.
    - Landline: (0X) XXXX XXXX format for state-based numbers.
    """

    entity_type: ClassVar[EntityType] = EntityType.AU_PHONE
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "medium"
    verification: ClassVar = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<PHONE>"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b(?:\+61\s?|0)4\d{2}[\s\-]?\d{3}[\s\-]?\d{3}\b"),
        re.compile(r"\b(?:\(0[2-9]\)\s?|0[2-9][\s\-]?)\d{4}[\s\-]?\d{4}\b"),
    ]
    context_words: ClassVar[list[str]] = [
        "phone",
        "mobile",
        "call",
        "contact",
        "tel",
        "telephone",
        "number",
    ]

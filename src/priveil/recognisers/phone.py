"""Generic (international) phone number recogniser."""

from __future__ import annotations

import re
from typing import ClassVar

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser


class PhoneRecogniser(RegexRecogniser):
    """Detect North American and international phone numbers.

    Complements AUPhoneRecogniser with broader international patterns.
    """

    entity_type: ClassVar[EntityType] = EntityType.PHONE_NUMBER
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "medium"
    verification: ClassVar = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<PHONE>"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b"),
    ]
    context_words: ClassVar[list[str]] = ["phone", "mobile", "cell", "tel"]

"""Email address recogniser."""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser


class EmailRecogniser(RegexRecogniser):
    """Detect email addresses using an RFC-5321-approximate pattern."""

    entity_type: ClassVar[EntityType] = EntityType.EMAIL_ADDRESS
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "medium"
    verification: ClassVar[Literal["trust", "advisor"]] = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<EMAIL>"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b", re.IGNORECASE),
    ]
    context_words: ClassVar[list[str]] = []

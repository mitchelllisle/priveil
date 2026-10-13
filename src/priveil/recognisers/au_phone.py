"""Australian mobile and landline phone number recogniser."""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser


class AUPhoneRecogniser(RegexRecogniser):
    """Detect Australian mobile and landline phone numbers.

    verification="judge": laya verifies spans in context, handling edge cases
    like product codes (XR-0412-345678) that regex alone can't distinguish.
    """

    entity_type: ClassVar[EntityType] = EntityType.AU_PHONE
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "medium"
    verification: ClassVar[Literal["trust", "judge"]] = "judge"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<PHONE>"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        # Mobile: 04XX (local or +61 prefix)
        re.compile(r"\b(?:\+61\s?|0)4\d{2}[\s\-]?\d{3}[\s\-]?\d{3}\b"),
        # Landline with parens: (0X) XXXX XXXX
        # \b fails before '(' (non-word char), so use negative lookbehind for \w
        re.compile(r"(?<!\w)\(0[2-9]\)\s?\d{4}[\s\-]?\d{4}"),
        # Landline without parens: 0X XXXX XXXX
        re.compile(r"\b0[2-9][\s\-]?\d{4}[\s\-]?\d{4}\b"),
    ]
    context_words: ClassVar[list[str]] = [
        "phone", "mobile", "call", "contact", "tel", "telephone", "number",
    ]

"""Generic (international) phone number recogniser."""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser


class PhoneRecogniser(RegexRecogniser):
    """Detect North American (NANP) and E.164-style international phone numbers.

    Complements AUPhoneRecogniser, which owns Australian domestic formats.
    """

    entity_type: ClassVar[EntityType] = EntityType.PHONE_NUMBER
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "medium"
    verification: ClassVar[Literal["trust", "advisor"]] = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "<PHONE>"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        # NANP. Lookarounds replace \b so a leading '+' is captured: \b cannot match
        # between a space and '+', both non-word. Parens are matched as a balanced
        # pair, otherwise "(212) 555-0123" yields the malformed span "212) 555-0123".
        re.compile(r"(?<!\w)(?:\+?1[-. ]?)?(?:\(\d{3}\)|\d{3})[-. ]?\d{3}[-. ]?\d{4}(?!\w)"),
        # International: '+' followed by 8-15 digits with optional separators.
        re.compile(r"(?<!\w)\+(?:\d[-. ]?){7,14}\d(?!\w)"),
    ]
    context_words: ClassVar[list[str]] = ["phone", "mobile", "cell", "tel"]

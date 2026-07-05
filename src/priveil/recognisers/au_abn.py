"""Australian Business Number (ABN) recogniser."""

from __future__ import annotations

import re
from typing import ClassVar

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser

# ATO mod-89 weights for the 11-digit ABN.
_ABN_WEIGHTS: tuple[int, ...] = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)


def _abn_checksum(digits: list[int]) -> bool:
    """Validate an 11-digit ABN using the ATO mod-89 algorithm.

    Args:
        digits: Exactly 11 integers.

    Returns:
        True if (first digit − 1, rest unchanged) weighted sum is divisible by 89.
    """
    if len(digits) != 11:
        return False
    adjusted = [digits[0] - 1, *digits[1:]]
    return sum(d * w for d, w in zip(adjusted, _ABN_WEIGHTS)) % 89 == 0


class AUABNRecogniser(RegexRecogniser):
    """Detect Australian Business Numbers (ABN).

    ABN is an 11-digit business identifier — not personal PII but tracked as a
    financial entity. Both patterns require checksum validation to avoid FP on
    any 11-digit sequence.
    """

    entity_type: ClassVar[EntityType] = EntityType.AU_ABN
    is_pii: ClassVar[bool] = False
    sensitivity: ClassVar[Sensitivity] = "low"
    verification: ClassVar = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "** *** *** ***"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b\d{2}[ \t]\d{3}[ \t]\d{3}[ \t]\d{3}\b"),
        re.compile(r"\b\d{11}\b"),
    ]
    context_words: ClassVar[list[str]] = [
        "abn",
        "australian business number",
        "business number",
    ]

    def _validate(self, text: str) -> bool | None:
        """Return True if mod-89 checksum passes, False to invalidate."""
        digits = [int(c) for c in text if c.isdigit()]
        return _abn_checksum(digits)

"""Australian Company Number (ACN) recogniser."""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser

# ASIC weights for the 9-digit ACN checksum (complement-of-10).
_ACN_WEIGHTS: tuple[int, ...] = (8, 7, 6, 5, 4, 3, 2, 1)


def _acn_checksum(digits: list[int]) -> bool:
    """Validate a 9-digit ACN using the ASIC complement-of-10 algorithm.

    Args:
        digits: Exactly 9 integers.

    Returns:
        True if (10 − weighted_sum % 10) % 10 == digits[8].
    """
    if len(digits) != 9:
        return False
    weighted_sum = sum(d * w for d, w in zip(digits[:8], _ACN_WEIGHTS))
    check = (10 - weighted_sum % 10) % 10
    return check == digits[8]


class AUACNRecogniser(RegexRecogniser):
    """Detect Australian Company Numbers (ACN).

    ACN is a 9-digit company identifier — not personal PII.
    """

    entity_type: ClassVar[EntityType] = EntityType.AU_ACN
    is_pii: ClassVar[bool] = False
    sensitivity: ClassVar[Sensitivity] = "low"
    verification: ClassVar[Literal["trust", "advisor"]] = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "*** *** ***"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b\d{3}[ \t]\d{3}[ \t]\d{3}\b"),
        re.compile(r"\b\d{9}\b"),
    ]
    context_words: ClassVar[list[str]] = [
        "acn",
        "australian company number",
        "company number",
        "company no",
    ]

    def _validate(self, text: str) -> bool | None:
        """Return True if ASIC checksum passes, False to invalidate."""
        digits = [int(c) for c in text if c.isdigit()]
        return _acn_checksum(digits)

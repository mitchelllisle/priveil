"""Australian Medicare card number recogniser."""

from __future__ import annotations

import re
from typing import ClassVar

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser

# Services Australia Medicare issuing algorithm weights (applied to first 8 digits).
_MEDICARE_WEIGHTS: tuple[int, ...] = (1, 3, 7, 9, 1, 3, 7, 9)


def _medicare_checksum(digits: list[int]) -> bool:
    """Validate a Medicare card number using the Services Australia algorithm.

    Args:
        digits: At least 9 integers (10th and 11th digits are issue/IRN suffixes).

    Returns:
        True if sum(first 8 digits * weights) mod 10 == 9th digit.
    """
    if len(digits) < 9:
        return False
    weighted_sum = sum(d * w for d, w in zip(digits[:8], _MEDICARE_WEIGHTS))
    return weighted_sum % 10 == digits[8]


class AUMedicareRecogniser(RegexRecogniser):
    """Detect Australian Medicare card numbers.

    Format: XXXX XXXXX X (first digit 2–6, 10 digits total, last is check digit).
    Critical PII — government health identifier.
    """

    entity_type: ClassVar[EntityType] = EntityType.AU_MEDICARE
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "critical"
    verification: ClassVar = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "**** *****-*"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b[2-6]\d{3}[ \t]\d{5}[ \t]\d\b"),
        re.compile(r"\b[2-6]\d{9}\b"),
    ]
    context_words: ClassVar[list[str]] = [
        "medicare",
        "medicare number",
        "medicare card",
        "health insurance",
        "dva",
    ]

    def _validate(self, text: str) -> bool | None:
        """Return True if checksum passes, False to invalidate."""
        digits = [int(c) for c in text if c.isdigit()]
        return _medicare_checksum(digits)

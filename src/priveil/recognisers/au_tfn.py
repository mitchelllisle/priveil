"""Australian Tax File Number (TFN) recogniser."""

from __future__ import annotations

import re
from typing import ClassVar

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser

# ATO-published weights for the 9-digit TFN checksum (mod 11).
_TFN_WEIGHTS: tuple[int, ...] = (1, 4, 3, 7, 5, 8, 6, 9, 10)


def _tfn_checksum(digits: list[int]) -> bool:
    """Validate a 9-digit TFN using the ATO mod-11 checksum.

    Args:
        digits: Exactly 9 integers extracted from the candidate string.

    Returns:
        True if the weighted sum is divisible by 11, False otherwise.
    """
    if len(digits) != 9:
        return False
    return sum(d * w for d, w in zip(digits, _TFN_WEIGHTS)) % 11 == 0


class AUTFNRecogniser(RegexRecogniser):
    """Detect Australian Tax File Numbers (TFN).

    Two patterns:
    - Spaced (XXX XXX XXX) — standard printed format.
    - Compact (9 digits) — less specific; context words and checksum reduce FP rate.

    Both patterns share the same base score (0.8); validation rejects any sequence
    that fails the ATO mod-11 checksum.
    """

    entity_type: ClassVar[EntityType] = EntityType.AU_TFN
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "critical"
    verification: ClassVar = "trust"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "***-***-***"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b\d{3}[ \t]\d{3}[ \t]\d{3}\b"),
        re.compile(r"\b\d{9}\b"),
    ]
    context_words: ClassVar[list[str]] = [
        "tfn",
        "tax file",
        "tax file number",
        "taxfile",
        "tax-file",
    ]

    def _validate(self, text: str) -> bool | None:
        """Return True if checksum passes, False to invalidate."""
        digits = [int(c) for c in text if c.isdigit()]
        return _tfn_checksum(digits)

"""Credit card number recogniser with Luhn checksum validation."""

from __future__ import annotations

import re
from typing import ClassVar

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm.

    Args:
        number: String containing only digit characters.

    Returns:
        True if the number passes the Luhn check.
    """
    digits = [int(c) for c in number if c.isdigit()]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class CreditCardRecogniser(RegexRecogniser):
    """Detect credit card numbers (Visa, Mastercard, Amex, Diners, Discover).

    Pattern covers the major card number formats. Every match is validated
    with the Luhn checksum to eliminate false positives from arbitrary digit strings.
    Operator masks the first 12 digits, leaving the last 4 visible.
    """

    entity_type: ClassVar[EntityType] = EntityType.CREDIT_CARD
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "critical"
    verification: ClassVar = "trust"
    default_operator: ClassVar[str] = "mask"
    default_operator_params: ClassVar[dict[str, object]] = {
        "masking_char": "*",
        "chars_to_mask": 12,
        "from_end": False,
    }

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r"\b(?:"
            r"4[0-9]{12}(?:[0-9]{3})?"          # Visa (13 or 16 digits)
            r"|5[1-5][0-9]{14}"                  # Mastercard
            r"|3[47][0-9]{13}"                   # Amex
            r"|3(?:0[0-5]|[68][0-9])[0-9]{11}"  # Diners Club
            r"|6(?:011|5[0-9]{2})[0-9]{12}"     # Discover
            r")\b"
        ),
    ]
    context_words: ClassVar[list[str]] = []

    def _validate(self, text: str) -> bool | None:
        """Reject matches that fail the Luhn checksum."""
        return _luhn_check(text)

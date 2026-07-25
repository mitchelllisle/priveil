"""Australian Bank State Branch (BSB) code recogniser."""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from priveil.domain.entities import EntityType, Sensitivity
from priveil.recognisers.base import RegexRecogniser


class AUBSBRecogniser(RegexRecogniser):
    """Detect Australian Bank State Branch (BSB) codes.

    Format: XXX-XXX (hyphen required). No checksum — BSB is a routing lookup.
    Low base score; context words are required to reach a meaningful confidence level.
    Verification is "advisor" because format-only detection yields many FP.
    """

    entity_type: ClassVar[EntityType] = EntityType.AU_BSB
    is_pii: ClassVar[bool] = True
    sensitivity: ClassVar[Sensitivity] = "high"
    verification: ClassVar[Literal["trust", "advisor"]] = "advisor"
    default_operator: ClassVar[str] = "replace"
    default_operator_params: ClassVar[dict[str, object]] = {"new_value": "XXX-XXX"}

    patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b\d{3}-\d{3}\b"),
    ]
    context_words: ClassVar[list[str]] = [
        "bsb",
        "bank state branch",
        "branch number",
        "bank code",
        "account",
        "transfer",
        "payment",
    ]

"""Recogniser registry: builds the ordered list of active recognisers."""

from __future__ import annotations

from typing import Any

from priveil.recognisers.au_abn import AUABNRecogniser
from priveil.recognisers.au_acn import AUACNRecogniser
from priveil.recognisers.au_bsb import AUBSBRecogniser
from priveil.recognisers.au_medicare import AUMedicareRecogniser
from priveil.recognisers.au_phone import AUPhoneRecogniser
from priveil.recognisers.au_tfn import AUTFNRecogniser
from priveil.recognisers.base import BaseRecogniser
from priveil.recognisers.credit_card import CreditCardRecogniser
from priveil.recognisers.date_time import DateTimeRecogniser
from priveil.recognisers.email import EmailRecogniser
from priveil.recognisers.location import LocationRecogniser
from priveil.recognisers.person import PersonRecogniser
from priveil.recognisers.phone import PhoneRecogniser


def build_recognisers(gliner_model: Any | None = None) -> list[BaseRecogniser]:
    """Build the ordered list of active recognisers.

    Order matters — higher-specificity recognisers (checksum-validated) come first so
    they take precedence when a span could match multiple entity types.

    Args:
        gliner_model: A GLiNER2 model instance. When provided, NER-based recognisers
            (PERSON, LOCATION, DATE_TIME) are included. Pass ``None`` to run in
            fast/regex-only mode — useful for unit tests and lightweight deployments.

    Returns:
        Ordered list of :class:`BaseRecogniser` instances.
    """
    recognisers: list[BaseRecogniser] = [
        # Checksum-validated: highest confidence, lowest FP rate.
        AUTFNRecogniser(),
        AUMedicareRecogniser(),
        AUABNRecogniser(),
        AUACNRecogniser(),
        # Format-only regex: reliable structure but no checksum.
        AUBSBRecogniser(),
        AUPhoneRecogniser(),
        EmailRecogniser(),
        CreditCardRecogniser(),
        PhoneRecogniser(),
    ]

    if gliner_model is not None:
        recognisers.extend([
            PersonRecogniser(gliner_model),
            LocationRecogniser(gliner_model),
            DateTimeRecogniser(gliner_model),
        ])

    return recognisers


def build_operator_configs(
    recognisers: list[BaseRecogniser],
) -> dict[str, tuple[str, dict[str, object]]]:
    """Return a mapping of entity_type → (operator_name, params) from recognisers.

    Used to populate the pseudonymiser with default operators derived from
    each recogniser's own declaration, so the config lives in one place.
    """
    return {
        r.entity_type.value: (r.default_operator, dict(r.default_operator_params))
        for r in recognisers
    }

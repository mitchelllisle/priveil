from enum import Enum
from typing import Literal

from pydantic import BaseModel

Sensitivity = Literal["low", "medium", "high", "critical"]


class EntityType(str, Enum):
    """Entity types recognised by the detection engine."""

    # Standard presidio / spaCy types
    PERSON = "PERSON"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHONE_NUMBER = "PHONE_NUMBER"
    CREDIT_CARD = "CREDIT_CARD"
    LOCATION = "LOCATION"
    DATE_TIME = "DATE_TIME"

    # Australian financial & government identifiers (slice 2)
    AU_TFN = "AU_TFN"            # Tax File Number — critical PII
    AU_ABN = "AU_ABN"            # Australian Business Number — not personal PII
    AU_ACN = "AU_ACN"            # Australian Company Number — not personal PII
    AU_BSB = "AU_BSB"            # Bank State Branch code (routing identifier)
    AU_ACCOUNT_NUMBER = "AU_ACCOUNT_NUMBER"  # Bank account number
    AU_MEDICARE = "AU_MEDICARE"  # Medicare card number — critical PII
    AU_PHONE = "AU_PHONE"        # Australian mobile / landline


class Entity(BaseModel, frozen=True):
    """A detected entity span with its position, classification, and confidence score."""

    text: str
    entity_type: EntityType
    start: int
    end: int
    score: float
    is_pii: bool
    sensitivity: Sensitivity
    # Set from the recogniser — determines whether this span needs advisor verification.
    verification: Literal["trust", "advisor"] = "trust"

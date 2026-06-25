from enum import Enum
from typing import Literal

from pydantic import BaseModel

Sensitivity = Literal["low", "medium", "high", "critical"]


class EntityType(str, Enum):
    """Entity types recognised by the detection engine.

    Standard presidio types only. Australian financial types are added in slice 2.
    """

    PERSON = "PERSON"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHONE_NUMBER = "PHONE_NUMBER"
    CREDIT_CARD = "CREDIT_CARD"
    LOCATION = "LOCATION"
    DATE_TIME = "DATE_TIME"
    NRP = "NRP"  # Nationality / religion / political group


# Business rules: (is_pii, sensitivity) for each recognised entity type.
# Every member of EntityType must have an entry — KeyError on lookup means
# the enum and this map are out of sync, which is a bug.
ENTITY_CLASSIFICATION: dict[EntityType, tuple[bool, Sensitivity]] = {
    EntityType.PERSON: (True, "high"),
    EntityType.EMAIL_ADDRESS: (True, "medium"),
    EntityType.PHONE_NUMBER: (True, "medium"),
    EntityType.CREDIT_CARD: (True, "critical"),
    EntityType.LOCATION: (True, "low"),
    EntityType.DATE_TIME: (False, "low"),
    EntityType.NRP: (False, "low"),
}


class Entity(BaseModel, frozen=True):
    """A detected entity span with its position, classification, and confidence score."""

    text: str
    entity_type: EntityType
    start: int
    end: int
    score: float
    is_pii: bool
    sensitivity: Sensitivity

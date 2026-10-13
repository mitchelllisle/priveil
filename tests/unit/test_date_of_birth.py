"""Unit tests for DateOfBirthRecogniser.

Verifies that personal birth dates are detected and scheduling/calendar
dates are not, using a mock model to avoid loading GLiNER2 weights.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from priveil.domain.entities import EntityType
from priveil.recognisers.date_of_birth import DateOfBirthRecogniser


# ── mock helpers ──────────────────────────────────────────────────────────────

def _recogniser(hits: dict[str, list[dict[str, Any]]]) -> DateOfBirthRecogniser:
    """Build a recogniser whose model returns the given entity hits."""
    model = MagicMock()
    model.extract_entities.return_value = {"entities": hits}
    return DateOfBirthRecogniser(model)


def _dob_hit(text: str, start: int, conf: float = 1.0) -> dict[str, Any]:
    return {"text": text, "start": start, "end": start + len(text), "confidence": conf}


def _no_hits() -> dict[str, list[dict[str, Any]]]:
    return {"date_of_birth": []}


# ── is_pii and sensitivity contract ──────────────────────────────────────────


def test_is_pii_true() -> None:
    assert DateOfBirthRecogniser.is_pii is True


def test_sensitivity_is_high() -> None:
    assert DateOfBirthRecogniser.sensitivity == "high"


def test_entity_type_is_date_of_birth() -> None:
    assert DateOfBirthRecogniser.entity_type == EntityType.DATE_OF_BIRTH


def test_default_operator_replaces_with_dob_placeholder() -> None:
    assert DateOfBirthRecogniser.default_operator == "replace"
    assert DateOfBirthRecogniser.default_operator_params["new_value"] == "<DOB>"


# ── positive cases: birth dates that SHOULD be detected ──────────────────────


class TestDetectedAsBirthDate:
    """Dates in personal birth-date context must be detected."""

    def test_birthday_with_year(self) -> None:
        """'my birthday is 2nd October 1967' — canonical DOB with year."""
        r = _recogniser({"date_of_birth": [_dob_hit("2nd October 1967", 15)]})
        spans = r.detect("my birthday is 2nd October 1967")
        assert len(spans) == 1
        assert spans[0].text == "2nd October 1967"

    def test_born_on_with_full_date(self) -> None:
        """'She was born on 14 March 1985'"""
        r = _recogniser({"date_of_birth": [_dob_hit("14 March 1985", 17)]})
        spans = r.detect("She was born on 14 March 1985")
        assert len(spans) == 1
        assert spans[0].text == "14 March 1985"

    def test_dob_prefix_numeric(self) -> None:
        """'DOB: 12/06/1990' — explicit label."""
        r = _recogniser({"date_of_birth": [_dob_hit("12/06/1990", 5)]})
        spans = r.detect("DOB: 12/06/1990")
        assert len(spans) == 1

    def test_date_of_birth_field(self) -> None:
        """'Patient date of birth: 15/08/1972'"""
        r = _recogniser({"date_of_birth": [_dob_hit("15/08/1972", 24)]})
        spans = r.detect("Patient date of birth: 15/08/1972")
        assert len(spans) == 1

    def test_born_in_year_only(self) -> None:
        r = _recogniser({"date_of_birth": [_dob_hit("1967", 18)]})
        spans = r.detect("John Smith was born in 1967")
        assert len(spans) == 1
        assert spans[0].text == "1967"


# ── negative cases: scheduling dates that must NOT be detected ────────────────


class TestNotDetectedAsScheduling:
    """Meeting/scheduling dates must not appear — the label is specific enough
    that the real GLiNER2 model returns nothing for these. Tests use an empty
    hits mock to document the contract."""

    def test_meeting_date_no_year(self) -> None:
        """'let's meet on the 2nd of October' — scheduling, no personal context."""
        r = _recogniser(_no_hits())
        spans = r.detect("let's meet on the 2nd of October")
        assert spans == []

    def test_deadline_date(self) -> None:
        r = _recogniser(_no_hits())
        spans = r.detect("The deadline is January 15th")
        assert spans == []

    def test_scheduled_call(self) -> None:
        r = _recogniser(_no_hits())
        spans = r.detect("Schedule a call for Tuesday 3pm")
        assert spans == []

    def test_invoice_date(self) -> None:
        r = _recogniser(_no_hits())
        spans = r.detect("The invoice is dated 01/03/2024")
        assert spans == []


# ── threshold gate ────────────────────────────────────────────────────────────


class TestThreshold:
    """Spans below gliner_threshold must be filtered out."""

    def test_low_confidence_hit_dropped(self) -> None:
        """Confidence 0.3 < threshold 0.5 — must be dropped."""
        r = _recogniser({"date_of_birth": [_dob_hit("2nd October 1967", 15, conf=0.3)]})
        spans = r.detect("my birthday is 2nd October 1967")
        assert spans == []

    def test_at_threshold_kept(self) -> None:
        """Confidence exactly at threshold must be kept."""
        r = _recogniser({"date_of_birth": [_dob_hit("2nd October 1967", 15, conf=0.5)]})
        spans = r.detect("my birthday is 2nd October 1967")
        assert len(spans) == 1

    def test_above_threshold_kept(self) -> None:
        """Score is capped at max_score (0.89) even if model returns higher."""
        r = _recogniser({"date_of_birth": [_dob_hit("12/06/1990", 5, conf=0.9)]})
        spans = r.detect("DOB: 12/06/1990")
        assert len(spans) == 1
        assert spans[0].score == pytest.approx(0.89)  # capped by GLiNERRecogniser.max_score

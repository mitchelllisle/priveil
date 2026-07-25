"""Property-based tests for pure functions using hypothesis.

Targets: AU recogniser checksum functions, engine operator/entity-map builders.
These functions have well-defined mathematical invariants published by the
issuing authorities (ATO, ASIC, Services Australia).
"""

from hypothesis import given
from hypothesis import strategies as st

from priveil.domain.entities import EntityType
from priveil.engine.pseudonymiser import _build_operators
from priveil.recognisers.au_abn import _abn_checksum
from priveil.recognisers.au_acn import _acn_checksum
from priveil.recognisers.au_medicare import _medicare_checksum
from priveil.recognisers.au_tfn import _tfn_checksum
from priveil.recognisers.registry import build_operator_configs, build_recognisers

# ── TFN ───────────────────────────────────────────────────────────────────────

@given(st.lists(st.integers(0, 9), min_size=0, max_size=20).filter(lambda d: len(d) != 9))
def test_tfn_checksum_wrong_length_always_false(digits: list[int]) -> None:
    """Any digit list that is not exactly 9 elements must return False."""
    assert _tfn_checksum(digits) is False


@given(st.lists(st.integers(0, 9), min_size=9, max_size=9))
def test_tfn_checksum_returns_bool(digits: list[int]) -> None:
    """Checksum always returns a bool, never raises."""
    result = _tfn_checksum(digits)
    assert isinstance(result, bool)


# ── ABN ───────────────────────────────────────────────────────────────────────

@given(st.lists(st.integers(0, 9), min_size=0, max_size=20).filter(lambda d: len(d) != 11))
def test_abn_checksum_wrong_length_always_false(digits: list[int]) -> None:
    """Any digit list that is not exactly 11 elements must return False."""
    assert _abn_checksum(digits) is False


@given(st.lists(st.integers(0, 9), min_size=11, max_size=11))
def test_abn_checksum_returns_bool(digits: list[int]) -> None:
    """Checksum always returns a bool, never raises."""
    result = _abn_checksum(digits)
    assert isinstance(result, bool)


# ── ACN ───────────────────────────────────────────────────────────────────────

@given(st.lists(st.integers(0, 9), min_size=0, max_size=20).filter(lambda d: len(d) != 9))
def test_acn_checksum_wrong_length_always_false(digits: list[int]) -> None:
    """Any digit list that is not exactly 9 elements must return False."""
    assert _acn_checksum(digits) is False


@given(st.lists(st.integers(0, 9), min_size=9, max_size=9))
def test_acn_checksum_returns_bool(digits: list[int]) -> None:
    """Checksum always returns a bool, never raises."""
    result = _acn_checksum(digits)
    assert isinstance(result, bool)


# ── Medicare ──────────────────────────────────────────────────────────────────

@given(st.lists(st.integers(0, 9), min_size=0, max_size=8))
def test_medicare_checksum_too_short_always_false(digits: list[int]) -> None:
    """Any digit list shorter than 9 must return False — checksum needs check digit at index 8."""
    assert _medicare_checksum(digits) is False


@given(st.lists(st.integers(0, 9), min_size=9, max_size=10))
def test_medicare_checksum_returns_bool(digits: list[int]) -> None:
    """Checksum always returns a bool, never raises."""
    result = _medicare_checksum(digits)
    assert isinstance(result, bool)


# ── _build_operators ──────────────────────────────────────────────────────────

_OPERATOR_VALUES = st.sampled_from(["replace", "mask", "redact", "hash"])
_ENTITY_KEYS = st.sampled_from([e.value for e in EntityType])


@given(st.dictionaries(_ENTITY_KEYS, _OPERATOR_VALUES, max_size=5))
def test_build_operators_overrides_applied(overrides: dict[str, str]) -> None:
    """Every override key must appear in the result with the requested operator."""
    from typing import cast

    from priveil.domain.pseudonymisation import OperatorType

    typed = {k: cast(OperatorType, v) for k, v in overrides.items()}
    result = _build_operators(typed, build_operator_configs(build_recognisers()))
    for entity_type, op_type in typed.items():
        assert entity_type in result
        assert result[entity_type].operator_name == op_type


@given(st.dictionaries(_ENTITY_KEYS, _OPERATOR_VALUES, max_size=5))
def test_build_operators_never_raises(overrides: dict[str, str]) -> None:
    """_build_operators must never raise regardless of override content."""
    from typing import cast

    from priveil.domain.pseudonymisation import OperatorType

    typed = {k: cast(OperatorType, v) for k, v in overrides.items()}
    _build_operators(typed, build_operator_configs(build_recognisers()))  # must not raise


# ── Recogniser completeness ────────────────────────────────────────────────────

def test_every_regex_recogniser_has_valid_sensitivity() -> None:
    """Every regex recogniser must declare a valid sensitivity and is_pii."""
    from priveil.recognisers.base import BaseRecogniser
    for rec in build_recognisers(gliner_model=None):
        assert isinstance(rec, BaseRecogniser)
        assert rec.sensitivity in {"low", "medium", "high", "critical"}
        assert isinstance(rec.is_pii, bool)
        assert rec.verification in {"trust", "advisor"}

"""Functional tests for MCP tools — real engines, no judge model."""

from __future__ import annotations

import pytest

from priveil.domain.detection import DetectionResult
from priveil.domain.entities import EntityType
from priveil.domain.pseudonymisation import PseudonymisationResult
from priveil.mcp.server import _State
from priveil.mcp.tools import anonymise, assess, detect
from tests.mcp.conftest import make_ctx


async def test_detect_returns_detection_result(engine_state: _State) -> None:
    result = await detect("Jane Smith TFN 123 456 782", ctx=make_ctx(engine_state))
    assert isinstance(result, DetectionResult)


async def test_detect_finds_person(engine_state: _State) -> None:
    result = await detect("Jane Smith", ctx=make_ctx(engine_state), mode="fast")
    assert any(e.entity_type == EntityType.PERSON for e in result.entities)


async def test_detect_finds_au_tfn(engine_state: _State) -> None:
    result = await detect("TFN 123 456 782", ctx=make_ctx(engine_state), mode="fast")
    assert any(e.entity_type == EntityType.AU_TFN for e in result.entities)


async def test_detect_clean_text_returns_no_entities(engine_state: _State) -> None:
    result = await detect("Interest rate is 5.5% per annum.", ctx=make_ctx(engine_state), mode="fast")
    assert result.entities == ()


async def test_detect_result_includes_audit_hash(engine_state: _State) -> None:
    result = await detect("some text", ctx=make_ctx(engine_state))
    assert result.input_hash.startswith("sha256:")


async def test_anonymise_returns_pseudonymisation_result(engine_state: _State) -> None:
    result = await anonymise("Jane Smith", ctx=make_ctx(engine_state))
    assert isinstance(result, PseudonymisationResult)


async def test_anonymise_replaces_person(engine_state: _State) -> None:
    result = await anonymise("Jane Smith", ctx=make_ctx(engine_state), mode="fast")
    assert "Jane Smith" not in result.anonymised_text
    assert "<PERSON>" in result.anonymised_text


async def test_anonymise_replaces_tfn(engine_state: _State) -> None:
    result = await anonymise("TFN 123 456 782", ctx=make_ctx(engine_state), mode="fast")
    assert "123 456 782" not in result.anonymised_text


async def test_anonymise_operator_override_redact(engine_state: _State) -> None:
    result = await anonymise(
        "Jane Smith",
        ctx=make_ctx(engine_state),
        mode="fast",
        operator_overrides={"PERSON": "redact"},
    )
    assert "Jane Smith" not in result.anonymised_text
    assert "<PERSON>" not in result.anonymised_text


async def test_anonymise_invalid_operator_raises(engine_state: _State) -> None:
    with pytest.raises(ValueError):
        await anonymise("Jane Smith", ctx=make_ctx(engine_state), operator_overrides={"PERSON": "explode"})


async def test_anonymise_entity_map_populated(engine_state: _State) -> None:
    result = await anonymise("Jane Smith", ctx=make_ctx(engine_state), mode="fast")
    assert "Jane Smith" in result.entity_map


async def test_assess_without_judge_model_raises(engine_state: _State) -> None:
    with pytest.raises(ValueError, match="PRIVEIL_JUDGE_MODEL"):
        await assess("Jane Smith TFN 123 456 782", ctx=make_ctx(engine_state))

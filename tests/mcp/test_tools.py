"""Functional tests for MCP tools — real engines, no advisor model."""

from __future__ import annotations

import pytest

from priveil.api.models import PriveilResponse
from priveil.domain.detection import DetectionData
from priveil.domain.entities import EntityType
from priveil.domain.pseudonymisation import PseudonymisationData
from priveil.mcp.server import _State
from priveil.mcp.tools import anonymise, assess, detect
from tests.mcp.conftest import make_ctx


async def test_detect_returns_priveil_response(engine_state: _State) -> None:
    result = await detect("My TFN is 123 456 782", ctx=make_ctx(engine_state))
    assert isinstance(result, PriveilResponse)
    assert isinstance(result.data, DetectionData)


async def test_detect_finds_email(engine_state: _State) -> None:
    result = await detect("Contact jane@example.com", ctx=make_ctx(engine_state), mode="fast")
    assert any(e.entity_type == EntityType.EMAIL_ADDRESS for e in result.data.entities)


async def test_detect_finds_au_tfn(engine_state: _State) -> None:
    result = await detect("TFN 123 456 782", ctx=make_ctx(engine_state), mode="fast")
    assert any(e.entity_type == EntityType.AU_TFN for e in result.data.entities)


async def test_detect_clean_text_returns_no_entities(engine_state: _State) -> None:
    result = await detect("Interest rate is 5.5% per annum.", ctx=make_ctx(engine_state), mode="fast")
    assert result.data.entities == ()


async def test_detect_result_includes_audit_hash(engine_state: _State) -> None:
    result = await detect("some text", ctx=make_ctx(engine_state))
    assert result.meta.response.input_hash is not None
    assert result.meta.response.input_hash.startswith("hmac-sha256:")


async def test_anonymise_returns_priveil_response(engine_state: _State) -> None:
    result = await anonymise("Contact jane@example.com", ctx=make_ctx(engine_state))
    assert isinstance(result, PriveilResponse)
    assert isinstance(result.data, PseudonymisationData)


async def test_anonymise_replaces_email(engine_state: _State) -> None:
    result = await anonymise("Contact jane@example.com", ctx=make_ctx(engine_state), mode="fast")
    assert "jane@example.com" not in result.data.anonymised_text
    assert "<EMAIL>" in result.data.anonymised_text


async def test_anonymise_replaces_tfn(engine_state: _State) -> None:
    result = await anonymise("TFN 123 456 782", ctx=make_ctx(engine_state), mode="fast")
    assert "123 456 782" not in result.data.anonymised_text


async def test_anonymise_operator_override_redact(engine_state: _State) -> None:
    result = await anonymise(
        "TFN 123 456 782",
        ctx=make_ctx(engine_state),
        mode="fast",
        operator_overrides={"AU_TFN": "redact"},
    )
    assert "123 456 782" not in result.data.anonymised_text
    assert "***-***-***" not in result.data.anonymised_text


async def test_anonymise_invalid_operator_raises(engine_state: _State) -> None:
    with pytest.raises(ValueError):
        await anonymise("jane@example.com", ctx=make_ctx(engine_state), operator_overrides={"EMAIL_ADDRESS": "explode"})


async def test_anonymise_entity_map_populated(engine_state: _State) -> None:
    result = await anonymise("Contact billing@acme.com for help", ctx=make_ctx(engine_state), mode="fast")
    assert "billing@acme.com" in result.data.entity_map


async def test_assess_without_advisor_model_raises(engine_state: _State) -> None:
    with pytest.raises(ValueError, match="PRIVEIL_ADVISOR_MODEL"):
        await assess("jane@example.com TFN 123 456 782", ctx=make_ctx(engine_state))

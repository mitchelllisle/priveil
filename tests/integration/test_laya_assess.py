"""Integration tests for laya-first dispatch on POST /assess.

Exercises the full laya assess path end-to-end via the HTTP client.
The laya router is mocked so no model download is needed.
"""

from httpx import AsyncClient


async def test_laya_assess_returns_200(laya_assess_client: AsyncClient) -> None:
    resp = await laya_assess_client.post("/assess", json={"text": "My TFN is 123 456 782"})
    assert resp.status_code == 200


async def test_laya_assess_response_shape(laya_assess_client: AsyncClient) -> None:
    resp = await laya_assess_client.post("/assess", json={"text": "Contact jane@example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert "meta" in body
    assert "data" in body
    assert body["meta"]["response"]["input_hash"].startswith("hmac-sha256:")
    # laya disclaimer, not LLM disclaimer
    disclaimer = body["meta"]["response"]["advisory_disclaimer"]
    assert "laya" in disclaimer.lower() or "rule-derived" in disclaimer.lower()
    data = body["data"]
    for field in ("overall_sensitivity", "risk_summary", "categories",
                  "regulatory_flags", "recommended_handling", "entity_breakdown", "reasoning"):
        assert field in data, f"missing field: {field}"


async def test_laya_assess_sensitivity_from_mock(laya_assess_client: AsyncClient) -> None:
    """Mock returns medium sensitivity; route should surface it."""
    resp = await laya_assess_client.post("/assess", json={"text": "some text"})
    assert resp.status_code == 200
    assert resp.json()["data"]["overall_sensitivity"] == "medium"


async def test_laya_assess_financial_category_from_noul(laya_assess_client: AsyncClient) -> None:
    """Mock returns is_financial=0.8; 'financial' should appear in categories."""
    resp = await laya_assess_client.post("/assess", json={"text": "Invoice amount $5000"})
    assert resp.status_code == 200
    assert "financial" in resp.json()["data"]["categories"]


async def test_laya_assess_entity_breakdown_populated(laya_assess_client: AsyncClient) -> None:
    resp = await laya_assess_client.post("/assess", json={"text": "TFN 123 456 782"})
    assert resp.status_code == 200
    breakdown = resp.json()["data"]["entity_breakdown"]
    types = {b["entity_type"] for b in breakdown}
    assert "AU_TFN" in types


async def test_laya_assess_no_assessor_503_mentions_laya(
    detect_client: AsyncClient,
) -> None:
    """Neither laya nor LLM configured → 503 with hint to install laya."""
    resp = await detect_client.post("/assess", json={"text": "some text"})
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "laya" in detail.lower() or "PRIVEIL_ADVISOR_MODEL" in detail

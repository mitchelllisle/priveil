"""Integration tests for POST /assess."""

from httpx import AsyncClient


async def test_assess_returns_200(assess_client: AsyncClient) -> None:
    resp = await assess_client.post(
        "/assess", json={"text": "My TFN is 123 456 782"}
    )
    assert resp.status_code == 200


async def test_assess_response_shape(assess_client: AsyncClient) -> None:
    resp = await assess_client.post(
        "/assess", json={"text": "Contact jane@example.com"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "meta" in body
    assert "data" in body
    assert "input_hash" in body["meta"]["response"]
    assert "advisory_disclaimer" in body["meta"]["response"]
    assert body["meta"]["response"]["input_hash"].startswith("hmac-sha256:")
    assert body["meta"]["response"]["advisory_disclaimer"] is not None
    data = body["data"]
    assert "overall_sensitivity" in data
    assert "risk_summary" in data
    assert "categories" in data
    assert "regulatory_flags" in data
    assert "recommended_handling" in data
    assert "entity_breakdown" in data
    assert "reasoning" in data
    assert isinstance(data["entity_breakdown"], list)
    # advisory_disclaimer has moved to meta — must not appear in data
    assert "advisory_disclaimer" not in data


async def test_assess_with_context(assess_client: AsyncClient) -> None:
    resp = await assess_client.post(
        "/assess",
        json={
            "text": "TFN 123 456 782 BSB 062-000",
            "context": "Australian home loan application",
        },
    )
    assert resp.status_code == 200


async def test_assess_with_pre_computed_detections(assess_client: AsyncClient) -> None:
    """Pre-computed detections (body['data']) should skip re-detection."""
    text = "jane@example.com"
    detect_resp = await assess_client.post("/detect", json={"text": text})
    assert detect_resp.status_code == 200

    assess_resp = await assess_client.post(
        "/assess",
        json={"text": text, "detections": detect_resp.json()["data"]},
    )
    assert assess_resp.status_code == 200
    assert "overall_sensitivity" in assess_resp.json()["data"]


async def test_assess_no_assessor_returns_503(detect_client: AsyncClient) -> None:
    """Client without assessor injected should return 503."""
    resp = await detect_client.post("/assess", json={"text": "some text"})
    assert resp.status_code == 503
    assert "PRIVEIL_JUDGE_MODEL" in resp.json()["detail"]


async def test_assess_empty_text_returns_422(assess_client: AsyncClient) -> None:
    resp = await assess_client.post("/assess", json={"text": ""})
    assert resp.status_code == 422


async def test_assess_entity_breakdown_populated(assess_client: AsyncClient) -> None:
    """entity_breakdown is computed from detections, not from the LLM."""
    text = "My name is Jane Smith and my TFN is 123 456 782"
    resp = await assess_client.post("/assess", json={"text": text})
    assert resp.status_code == 200
    breakdown = resp.json()["data"]["entity_breakdown"]
    types = {b["entity_type"] for b in breakdown}
    # TFN and PERSON should both appear
    assert "AU_TFN" in types
    assert "PERSON" in types


async def test_assess_clean_text_low_sensitivity(assess_client: AsyncClient) -> None:
    """No PII → breakdown empty; LLM (TestModel) returns its default sensitivity."""
    resp = await assess_client.post(
        "/assess", json={"text": "Fixed home loan repayments are calculated monthly."}
    )
    assert resp.status_code == 200
    # breakdown should be empty — no PII entities
    assert resp.json()["data"]["entity_breakdown"] == []

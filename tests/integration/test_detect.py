"""Integration tests for POST /detect.

All tests run against the full ASGI app with the real presidio/spaCy engine
injected via detect_client. No mocks.
"""

from httpx import AsyncClient


async def test_detect_returns_200(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={"text": "Email me at test@example.com"})
    assert resp.status_code == 200


async def test_detect_response_shape(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={"text": "Call Jane at jane@example.com"})
    body = resp.json()
    assert "meta" in body
    assert "data" in body
    assert "request" in body["meta"]
    assert "response" in body["meta"]
    assert "mode" in body["meta"]["request"]
    assert "mode" in body["meta"]["response"]
    assert "input_hash" in body["meta"]["response"]
    assert "entities" in body["data"]
    assert body["meta"]["response"]["input_hash"].startswith("hmac-sha256:")


async def test_detect_email_entity(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={"text": "Reach us at billing@acme.com.au"})
    types = {e["entity_type"] for e in resp.json()["data"]["entities"]}
    assert "EMAIL_ADDRESS" in types


async def test_detect_excludes_legacy_8_digit_tfn(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={"text": "Legacy TFN 12 345 678", "mode": "fast"})
    types = {e["entity_type"] for e in resp.json()["data"]["entities"]}
    assert "AU_TFN" not in types


async def test_detect_entity_fields_present(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={"text": "Email is hello@test.com"})
    entities = resp.json()["data"]["entities"]
    assert len(entities) > 0
    for entity in entities:
        assert "text" in entity
        assert "entity_type" in entity
        assert "start" in entity
        assert "end" in entity
        assert "score" in entity
        assert "is_pii" in entity
        assert "sensitivity" in entity


async def test_detect_email_is_pii(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={"text": "Send to user@domain.com"})
    emails = [e for e in resp.json()["data"]["entities"] if e["entity_type"] == "EMAIL_ADDRESS"]
    assert all(e["is_pii"] for e in emails)
    assert all(e["sensitivity"] == "medium" for e in emails)


async def test_detect_input_hash_deterministic(detect_client: AsyncClient) -> None:
    payload = {"text": "Jane Smith works at ACME"}
    r1 = await detect_client.post("/detect", json=payload)
    r2 = await detect_client.post("/detect", json=payload)
    assert r1.json()["meta"]["response"]["input_hash"] == r2.json()["meta"]["response"]["input_hash"]


async def test_detect_judge_mode_surfaces_fallback_when_unconfigured(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={"text": "Jane Smith", "mode": "judge"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["request"]["mode"] == "judge"
    assert body["meta"]["response"]["mode"] == "fast"


async def test_detect_empty_text_returns_422(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={"text": ""})
    assert resp.status_code == 422


async def test_detect_missing_text_returns_422(detect_client: AsyncClient) -> None:
    resp = await detect_client.post("/detect", json={})
    assert resp.status_code == 422

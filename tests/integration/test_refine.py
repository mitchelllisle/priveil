"""Integration tests for mode='advisor'/'fast' on /detect and /pseudonymise.

Tests use the advised_client fixture which has a pass-through SpanAdvisor injected.
The advisor returns all entities unchanged, so detection results are unaffected —
but the mode='advisor' path runs end-to-end without real LLM calls.
"""

from httpx import AsyncClient

# ── /detect with mode ────────────────────────────────────────────────────────


async def test_detect_refine_true_runs_without_error(advised_client: AsyncClient) -> None:
    resp = await advised_client.post("/detect", json={"text": "Jane Smith jane@example.com", "mode": "advisor"})
    assert resp.status_code == 200
    assert "entities" in resp.json()["data"]
    assert resp.json()["data"]["advisor_applied"] is True


async def test_detect_refine_false_skips_refiner(advised_client: AsyncClient) -> None:
    """refine=false must work even when advisor is configured."""
    resp = await advised_client.post("/detect", json={"text": "Jane Smith", "mode": "fast"})
    assert resp.status_code == 200
    assert resp.json()["data"]["advisor_applied"] is False


async def test_detect_no_refiner_refine_true_silently_skips(detect_client: AsyncClient) -> None:
    """When no advisor is configured, mode="advisor" is silently ignored."""
    resp = await detect_client.post("/detect", json={"text": "Jane Smith jane@example.com", "mode": "advisor"})
    assert resp.status_code == 200
    assert len(resp.json()["data"]["entities"]) > 0
    assert resp.json()["data"]["advisor_applied"] is False


async def test_detect_mode_defaults_to_advisor(detect_client: AsyncClient) -> None:
    """Omitting mode should default to 'advisor' (silently skipped without advisor configured)."""
    resp = await detect_client.post("/detect", json={"text": "jane@example.com"})
    assert resp.status_code == 200


# ── /pseudonymise with mode ───────────────────────────────────────────────────


async def test_pseudonymise_refine_true_runs_without_error(advised_client: AsyncClient) -> None:
    resp = await advised_client.post("/pseudonymise", json={"text": "Jane Smith TFN 123 456 782", "mode": "advisor"})
    assert resp.status_code == 200
    assert "anonymised_text" in resp.json()["data"]
    assert resp.json()["data"]["advisor_applied"] is True


async def test_pseudonymise_refine_false_skips_refiner(advised_client: AsyncClient) -> None:
    resp = await advised_client.post("/pseudonymise", json={"text": "Jane Smith", "mode": "fast"})
    assert resp.status_code == 200
    assert resp.json()["data"]["advisor_applied"] is False


async def test_pseudonymise_no_refiner_refine_true_silently_skips(pseudonymise_client: AsyncClient) -> None:
    resp = await pseudonymise_client.post("/pseudonymise", json={"text": "jane@example.com", "mode": "advisor"})
    assert resp.status_code == 200
    assert "jane@example.com" not in resp.json()["data"]["anonymised_text"]
    assert resp.json()["data"]["advisor_applied"] is False

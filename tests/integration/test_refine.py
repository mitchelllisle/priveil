"""Integration tests for refine=true on /detect and /anonymise.

Tests use the refined_client fixture which has a TestModel refiner injected.
TestModel returns empty lists (no FPs, no FNs), so the detection result is
unchanged — but the refiner path runs end-to-end without error.
"""

from httpx import AsyncClient

# ── /detect with refine ───────────────────────────────────────────────────────

async def test_detect_refine_true_runs_without_error(refined_client: AsyncClient) -> None:
    resp = await refined_client.post(
        "/detect", json={"text": "Jane Smith jane@example.com", "refine": True}
    )
    assert resp.status_code == 200
    assert "entities" in resp.json()


async def test_detect_refine_false_skips_refiner(refined_client: AsyncClient) -> None:
    """refine=false must work even when refiner is configured."""
    resp = await refined_client.post(
        "/detect", json={"text": "Jane Smith", "refine": False}
    )
    assert resp.status_code == 200


async def test_detect_no_refiner_refine_true_silently_skips(detect_client: AsyncClient) -> None:
    """When no refiner is configured, refine=True is silently ignored."""
    resp = await detect_client.post(
        "/detect", json={"text": "Jane Smith jane@example.com", "refine": True}
    )
    assert resp.status_code == 200
    assert len(resp.json()["entities"]) > 0


async def test_detect_refine_default_is_true(detect_client: AsyncClient) -> None:
    """Omitting refine should default to True (silently skipped without refiner)."""
    resp = await detect_client.post("/detect", json={"text": "jane@example.com"})
    assert resp.status_code == 200


# ── /anonymise with refine ────────────────────────────────────────────────────

async def test_anonymise_refine_true_runs_without_error(refined_client: AsyncClient) -> None:
    resp = await refined_client.post(
        "/anonymise", json={"text": "Jane Smith TFN 123 456 782", "refine": True}
    )
    assert resp.status_code == 200
    assert "anonymised_text" in resp.json()


async def test_anonymise_refine_false_skips_refiner(refined_client: AsyncClient) -> None:
    resp = await refined_client.post(
        "/anonymise", json={"text": "Jane Smith", "refine": False}
    )
    assert resp.status_code == 200


async def test_anonymise_no_refiner_refine_true_silently_skips(anonymise_client: AsyncClient) -> None:
    resp = await anonymise_client.post(
        "/anonymise", json={"text": "jane@example.com", "refine": True}
    )
    assert resp.status_code == 200
    assert "jane@example.com" not in resp.json()["anonymised_text"]

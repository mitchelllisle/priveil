"""Integration tests for mode='judge'/'fast' on /detect and /pseudonymise.

Tests use the judged_client fixture which has a pass-through SpanJudge injected.
The judge returns all entities unchanged, so detection results are unaffected —
but the mode='judge' path runs end-to-end without real LLM calls.
"""

from httpx import AsyncClient

# ── /detect with mode ────────────────────────────────────────────────────────


async def test_detect_refine_true_runs_without_error(judged_client: AsyncClient) -> None:
    resp = await judged_client.post("/detect", json={"text": "Jane Smith jane@example.com", "mode": "judge"})
    assert resp.status_code == 200
    assert "entities" in resp.json()["data"]
    assert resp.json()["data"]["judge_applied"] is True


async def test_detect_refine_false_skips_refiner(judged_client: AsyncClient) -> None:
    """refine=false must work even when judge is configured."""
    resp = await judged_client.post("/detect", json={"text": "Jane Smith", "mode": "fast"})
    assert resp.status_code == 200
    assert resp.json()["data"]["judge_applied"] is False


async def test_detect_no_refiner_refine_true_silently_skips(detect_client: AsyncClient) -> None:
    """When no judge is configured, mode="judge" is silently ignored."""
    resp = await detect_client.post("/detect", json={"text": "Jane Smith jane@example.com", "mode": "judge"})
    assert resp.status_code == 200
    assert len(resp.json()["data"]["entities"]) > 0
    assert resp.json()["data"]["judge_applied"] is False


async def test_detect_mode_defaults_to_judge(detect_client: AsyncClient) -> None:
    """Omitting mode should default to 'judge' (silently skipped without judge configured)."""
    resp = await detect_client.post("/detect", json={"text": "jane@example.com"})
    assert resp.status_code == 200


# ── /pseudonymise with mode ───────────────────────────────────────────────────


async def test_pseudonymise_refine_true_runs_without_error(judged_client: AsyncClient) -> None:
    resp = await judged_client.post("/pseudonymise", json={"text": "Jane Smith TFN 123 456 782", "mode": "judge"})
    assert resp.status_code == 200
    assert "anonymised_text" in resp.json()["data"]
    assert resp.json()["data"]["judge_applied"] is True


async def test_pseudonymise_refine_false_skips_refiner(judged_client: AsyncClient) -> None:
    resp = await judged_client.post("/pseudonymise", json={"text": "Jane Smith", "mode": "fast"})
    assert resp.status_code == 200
    assert resp.json()["data"]["judge_applied"] is False


async def test_pseudonymise_no_refiner_refine_true_silently_skips(pseudonymise_client: AsyncClient) -> None:
    resp = await pseudonymise_client.post("/pseudonymise", json={"text": "jane@example.com", "mode": "judge"})
    assert resp.status_code == 200
    assert "jane@example.com" not in resp.json()["data"]["anonymised_text"]
    assert resp.json()["data"]["judge_applied"] is False

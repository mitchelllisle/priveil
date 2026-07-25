"""Unit tests for SpanAdvisor.advise() routing logic.

Isolates the advisor from any real LLM by mocking ``_verify_advisor`` —
the internal coroutine that calls the pydantic-ai Agent.  Every test
asserts on observable contract:

  - trust-routed entities and high-score entities bypass the advisor.
  - advisor-routed low-score entities are passed to ``_verify_advisor``.
  - The LLM can drop false positives (only kept ids survive).
  - Errors in the LLM call trigger fail-open: all spans returned, advisor_applied=False.
  - Integration path: the advised_client fixture wires the pass-through advisor;
    advisor_applied must be True in the HTTP response when advisor-tier spans are present.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from priveil.advisor.span_advisor import SpanAdvisor
from priveil.domain.entities import Entity, EntityType
from priveil.settings import Settings

# ── test helpers ──────────────────────────────────────────────────────────────


def _settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


def _entity(
    *,
    entity_type: EntityType = EntityType.EMAIL_ADDRESS,
    text: str = "user@example.com",
    start: int = 0,
    score: float = 0.85,
    verification: str = "trust",
) -> Entity:
    sensitivity_map = {
        EntityType.EMAIL_ADDRESS: "medium",
        EntityType.AU_TFN: "critical",
        EntityType.AU_MEDICARE: "critical",
        EntityType.AU_BSB: "high",
        EntityType.AU_ABN: "low",
        EntityType.AU_PHONE: "medium",
        EntityType.CREDIT_CARD: "critical",
    }
    is_pii_map = {
        EntityType.EMAIL_ADDRESS: True,
        EntityType.AU_TFN: True,
        EntityType.AU_MEDICARE: True,
        EntityType.AU_BSB: True,
        EntityType.AU_ABN: False,
        EntityType.AU_PHONE: True,
        EntityType.CREDIT_CARD: True,
    }
    return Entity(
        text=text,
        entity_type=entity_type,
        start=start,
        end=start + len(text),
        score=score,
        is_pii=is_pii_map.get(entity_type, True),
        sensitivity=sensitivity_map.get(entity_type, "medium"),
        verification=verification,  # type: ignore[arg-type]
    )


def _advisor_with_spy(settings: Settings | None = None) -> tuple[SpanAdvisor, AsyncMock]:
    """Return an advisor whose ``_verify_advisor`` is replaced by a spy that keeps everything."""
    s = settings or _settings()
    advisor = SpanAdvisor(agent=MagicMock(), settings=s)
    spy = AsyncMock(side_effect=lambda text, spans: (list(spans), True))
    advisor._verify_advisor = spy  # type: ignore[method-assign]
    return advisor, spy


# ── routing: trust bypass ──────────────────────────────────────────────────────


class TestTrustBypass:
    """Trust-verified entities must never reach the LLM advisor."""

    async def test_all_trust_entities_bypass_advisor(self) -> None:
        advisor, spy = _advisor_with_spy()
        entities = (
            _entity(entity_type=EntityType.EMAIL_ADDRESS, verification="trust"),
            _entity(entity_type=EntityType.AU_TFN, text="123 456 782", start=20,
                    score=0.95, verification="trust"),
        )
        result = await advisor.advise("user@example.com some text 123 456 782", entities)
        spy.assert_not_called()
        assert result.advisor_applied is False
        assert len(result.entities) == 2

    async def test_single_trust_entity_returns_unchanged(self) -> None:
        advisor, spy = _advisor_with_spy()
        entity = _entity(verification="trust", score=0.80)
        result = await advisor.advise("user@example.com", (entity,))
        spy.assert_not_called()
        assert result.entities == (entity,)

    async def test_empty_entities_no_advisor_call(self) -> None:
        advisor, spy = _advisor_with_spy()
        result = await advisor.advise("some text with no PII", ())
        spy.assert_not_called()
        assert result.advisor_applied is False
        assert result.entities == ()


# ── routing: score threshold bypass ───────────────────────────────────────────


class TestScoreThresholdBypass:
    """Advisor-tier entities scoring >= advisor_score_threshold bypass the LLM."""

    async def test_high_score_advisor_entity_bypasses(self) -> None:
        # advisor_score_threshold defaults to 0.9; score=0.95 → certain tier
        s = _settings(advisor_score_threshold=0.9)
        advisor, spy = _advisor_with_spy(s)
        entity = _entity(
            entity_type=EntityType.AU_BSB,
            text="062-000",
            score=0.95,
            verification="advisor",
        )
        result = await advisor.advise("BSB 062-000 transfer", (entity,))
        spy.assert_not_called()
        assert result.advisor_applied is False
        assert entity in result.entities

    async def test_score_exactly_at_threshold_bypasses(self) -> None:
        s = _settings(advisor_score_threshold=0.9)
        advisor, spy = _advisor_with_spy(s)
        entity = _entity(score=0.9, verification="advisor")
        result = await advisor.advise("text", (entity,))
        spy.assert_not_called()
        assert result.advisor_applied is False

    async def test_score_just_below_threshold_routes_to_advisor(self) -> None:
        s = _settings(advisor_score_threshold=0.9)
        advisor, spy = _advisor_with_spy(s)
        entity = _entity(
            entity_type=EntityType.AU_BSB,
            text="062-000",
            score=0.8,  # base score, no context boost
            verification="advisor",
        )
        result = await advisor.advise("The sequence 062-000 is here", (entity,))
        spy.assert_called_once()
        assert result.advisor_applied is True


# ── routing: advisor call semantics ───────────────────────────────────────────


class TestAdvisorCallSemantics:
    """When the LLM advisor is called, verify what it receives and how results are merged."""

    async def test_only_advisor_tier_entities_sent_to_llm(self) -> None:
        """Trust and high-score entities must NOT be forwarded to the LLM."""
        s = _settings(advisor_score_threshold=0.9)
        advisor, spy = _advisor_with_spy(s)

        trust_entity = _entity(verification="trust", score=0.85)
        advisor_entity = _entity(
            entity_type=EntityType.AU_BSB,
            text="062-000",
            start=30,
            score=0.8,
            verification="advisor",
        )
        await advisor.advise("user@example.com some text 062-000", (trust_entity, advisor_entity))

        spy.assert_called_once()
        _, call_spans = spy.call_args[0]  # positional args: (text, spans)
        assert advisor_entity in call_spans
        assert trust_entity not in call_spans

    async def test_merged_result_sorted_by_start(self) -> None:
        """After advising, entities from both tiers must be sorted by start offset."""
        s = _settings(advisor_score_threshold=0.9)
        advisor, spy = _advisor_with_spy(s)

        e_trust = _entity(start=50, verification="trust")
        e_advisor = _entity(
            entity_type=EntityType.AU_BSB, text="062-000", start=5, score=0.8, verification="advisor"
        )
        result = await advisor.advise("x" * 60, (e_trust, e_advisor))
        starts = [e.start for e in result.entities]
        assert starts == sorted(starts)

    async def test_advisor_can_drop_false_positive(self) -> None:
        """Advisor that keeps only ID 0 must drop ID 1 from the result."""
        s = _settings(advisor_score_threshold=0.9)
        advisor = SpanAdvisor(agent=MagicMock(), settings=s)

        e0 = _entity(entity_type=EntityType.AU_BSB, text="062-000", start=0, score=0.8, verification="advisor")
        e1 = _entity(entity_type=EntityType.AU_BSB, text="123-456", start=20, score=0.8, verification="advisor")

        # Spy returns only e0 (index 0 kept, index 1 dropped)
        async def keep_first(text: str, spans: list) -> tuple:
            return [spans[0]], True

        advisor._verify_advisor = keep_first  # type: ignore[method-assign]
        result = await advisor.advise("062-000 some text 123-456", (e0, e1))
        assert e0 in result.entities
        assert e1 not in result.entities
        assert result.advisor_applied is True

    async def test_advisor_can_keep_all_spans(self) -> None:
        """When the LLM keeps every span, all must appear in the result."""
        s = _settings(advisor_score_threshold=0.9)
        advisor, _ = _advisor_with_spy(s)

        entities = tuple(
            _entity(
                entity_type=EntityType.AU_BSB,
                text=f"06{i}-000",
                start=i * 10,
                score=0.8,
                verification="advisor",
            )
            for i in range(3)
        )
        result = await advisor.advise("x" * 50, entities)
        assert len(result.entities) == 3
        assert result.advisor_applied is True

    async def test_advisor_can_drop_all_spans(self) -> None:
        """When the LLM drops every span, only trust entities remain."""
        s = _settings(advisor_score_threshold=0.9)
        advisor = SpanAdvisor(agent=MagicMock(), settings=s)

        trust_entity = _entity(verification="trust", score=0.85)
        advisor_entity = _entity(
            entity_type=EntityType.AU_BSB, text="062-000", start=20, score=0.8, verification="advisor"
        )

        async def drop_all(text: str, spans: list) -> tuple:
            return [], True  # LLM decides all are false positives

        advisor._verify_advisor = drop_all  # type: ignore[method-assign]
        result = await advisor.advise("user@example.com text 062-000", (trust_entity, advisor_entity))
        # advisor_entity dropped; trust_entity kept
        assert trust_entity in result.entities
        assert advisor_entity not in result.entities
        assert result.advisor_applied is True


# ── fail-open behaviour ────────────────────────────────────────────────────────


class TestFailOpen:
    """Errors in the LLM agent call must not drop any spans — fail-open is safety-first.

    The exception is caught inside ``_verify_advisor``; tests must mock ``agent.run``
    (not ``_verify_advisor``) so the real catch block executes.
    """

    async def test_llm_exception_keeps_all_spans(self) -> None:
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        s = _settings(advisor_score_threshold=0.9)
        advisor = SpanAdvisor(agent=mock_agent, settings=s)

        advisor_entity = _entity(
            entity_type=EntityType.AU_BSB, text="062-000", score=0.8, verification="advisor"
        )
        result = await advisor.advise("BSB 062-000", (advisor_entity,))
        # fail-open: entity must be kept
        assert advisor_entity in result.entities
        # applied must be False — the advisor did not successfully run
        assert result.advisor_applied is False

    async def test_llm_timeout_keeps_all_spans(self) -> None:
        """asyncio.TimeoutError (from advisor_timeout_ms) must also trigger fail-open."""
        import asyncio

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=asyncio.TimeoutError())

        s = _settings(advisor_score_threshold=0.9)
        advisor = SpanAdvisor(agent=mock_agent, settings=s)

        advisor_entity = _entity(
            entity_type=EntityType.AU_BSB, text="062-000", score=0.8, verification="advisor"
        )
        result = await advisor.advise("BSB 062-000", (advisor_entity,))
        assert advisor_entity in result.entities
        assert result.advisor_applied is False


# ── integration: HTTP response reflects advisor path ──────────────────────────


class TestAdvisorIntegration:
    """End-to-end: HTTP response reflects advisor routing correctly.

    ``advised_client`` injects ``_PassThroughAdvisor``, which always returns
    ``advisor_applied=True`` from its ``advise()`` override.
    ``detect_client`` has no advisor; mode='advisor' silently falls back to fast.
    """

    async def test_no_advisor_wired_returns_advisor_applied_false(
        self, detect_client: AsyncClient
    ) -> None:
        # No advisor in detect_client → route falls back to fast, advisor_applied=False
        resp = await detect_client.post(
            "/detect", json={"text": "TFN 123 456 782", "mode": "advisor"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["advisor_applied"] is False
        # mode_used must downgrade to fast when no advisor is wired
        assert body["meta"]["response"]["mode"] == "fast"
        assert body["meta"]["request"]["mode"] == "advisor"

    async def test_advisor_wired_sets_applied_true_for_advisor_tier_span(
        self, advised_client: AsyncClient
    ) -> None:
        # BSB without context → score 0.8 < threshold 0.9 → advisor-tier
        # _PassThroughAdvisor.advise() returns advisor_applied=True
        resp = await advised_client.post(
            "/detect",
            json={"text": "The routing number 062-000 is used here", "mode": "advisor"},
        )
        assert resp.status_code == 200
        body = resp.json()
        types = {e["entity_type"] for e in body["data"]["entities"]}
        assert "AU_BSB" in types
        assert body["data"]["advisor_applied"] is True

    async def test_fast_mode_skips_advisor_regardless_of_wiring(
        self, advised_client: AsyncClient
    ) -> None:
        """mode='fast' bypasses the advisor even when one is wired."""
        resp = await advised_client.post(
            "/detect",
            json={"text": "Routing 062-000 transfer", "mode": "fast"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["advisor_applied"] is False

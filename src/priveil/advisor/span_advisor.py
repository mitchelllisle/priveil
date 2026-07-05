"""Internal span-verdict advisor for /detect and /pseudonymise.

Entity spans are routed to one of two tiers:

  trust   — kept as-is (trust-verified recogniser or score at/above advisor_score_threshold).
  advisor — submitted to the LLM advisor for contextual verification.

When the LLM advisor is unavailable (PRIVEIL_ADVISOR_MODEL not set) the advisor
tier degrades conservatively — spans are kept rather than silently dropped.

All LLM calls go through pydantic-ai so structured output is type-safe and
consistent with the assessor path.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic_ai import Agent

from priveil.domain.entities import Entity

if TYPE_CHECKING:
    from priveil.settings import Settings

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
SPAN_ADVISOR_SYSTEM_PROMPT: str = (_PROMPTS_DIR / "span_advisor.md").read_text(encoding="utf-8").strip()


class AdvisorResult(BaseModel, frozen=True):
    """Result of a span-verdict advise pass."""

    entities: tuple[Entity, ...]
    advisor_applied: bool


class KeepDecision(BaseModel, frozen=True):
    """Structured output from the span-verdict LLM call.

    ``keep`` holds the ids of spans the advisor considers genuine PII.
    Omitted ids are dropped as false positives.
    """

    keep: list[int]


class SpanAdvisor:
    """Span-verdict advisor backed by a pydantic-ai Agent.

    Separates entity spans into two tiers — trust (pass through) and advisor
    (submitted to the LLM) — then merges the confirmed spans with the trusted
    set, sorted by start offset.
    """

    def __init__(self, agent: "Agent[None, KeepDecision]", settings: "Settings") -> None:
        self._agent = agent
        self._settings = settings

    async def advise(self, text: str, entities: tuple[Entity, ...]) -> AdvisorResult:
        """Verify uncertain spans and return the filtered entity set.

        Args:
            text: The original document text (used to build span context windows).
            entities: All detected entities, trust and advisor-routed alike.

        Returns:
            AdvisorResult with the confirmed entity set and an applied flag.
        """
        s = self._settings
        certain: list[Entity] = []
        advisor_spans: list[Entity] = []

        for entity in entities:
            # trust-routed entities always bypass; high-confidence scores bypass regardless of route.
            if entity.verification == "trust" or entity.score >= s.advisor_score_threshold:
                certain.append(entity)
            else:
                advisor_spans.append(entity)

        if not advisor_spans:
            return AdvisorResult(entities=tuple(certain), advisor_applied=False)

        kept, applied = await self._verify_advisor(text, advisor_spans)
        merged = sorted(certain + kept, key=lambda e: e.start)
        return AdvisorResult(entities=tuple(merged), advisor_applied=applied)

    # ── verification path ─────────────────────────────────────────────────────

    async def _verify_advisor(self, text: str, spans: list[Entity]) -> tuple[list[Entity], bool]:
        """Submit spans to the LLM advisor; fail-open on any error.

        Returns:
            (kept_entities, applied) — applied is False when failing open.
        """
        s = self._settings
        payload = [
            {
                "id": i,
                "type": entity.entity_type.value,
                "span": entity.text,
                "context": text[max(0, entity.start - s.advisor_context_chars) : entity.end + s.advisor_context_chars],
            }
            for i, entity in enumerate(spans)
        ]
        try:
            async with asyncio.timeout(s.advisor_timeout_ms / 1000):
                result = await self._agent.run(
                    json.dumps(payload),
                    model_settings={"max_tokens": s.advisor_max_tokens},
                )
            keep_ids = {int(i) for i in result.output.keep}
            return [entity for i, entity in enumerate(spans) if i in keep_ids], True
        except Exception:
            logger.exception(
                "Span advisor failed; keeping all %d span(s) (fail-open)", len(spans)
            )
            return spans, False  # conservative: keep all on any error


def build_span_advisor(settings: "Settings") -> SpanAdvisor:
    """Build the span-verdict advisor from settings.

    Args:
        settings: Application settings with advisor_model configured.

    Returns:
        SpanAdvisor backed by a pydantic-ai Agent with KeepDecision structured output.

    Raises:
        ValueError: If advisor_model is not set in settings.
    """
    from priveil.advisor.model import build_advisor_model

    model = build_advisor_model(settings)
    agent: Agent[None, KeepDecision] = Agent(
        model=model,
        output_type=KeepDecision,
        system_prompt=SPAN_ADVISOR_SYSTEM_PROMPT,
        model_settings={"temperature": settings.advisor_temperature},
    )
    return SpanAdvisor(agent=agent, settings=settings)

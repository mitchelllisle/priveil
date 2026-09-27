"""Laya-backed span advisor — System 1 non-autoregressive PII verification.

Replaces the pydantic-ai LLM advisor for mode='advisor' span verification.
Uses laya's Router with noul (yes/no likelihood) questions to verify whether
detected spans are genuine PII. Typical latency: ~33 ms per span on CPU.

Requires: uv sync --extra laya
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from priveil.advisor.span_advisor import AdvisorResult
from priveil.domain.entities import Entity

if TYPE_CHECKING:
    from priveil.settings import Settings

logger = logging.getLogger(__name__)

_VERIFY_QUESTION: dict[str, Any] = {
    "is_genuine_pii": {
        "type": "noul",
        "instructions": (
            "Is the detected span a genuine real-world PII entity of the stated type "
            "that should be redacted to protect someone's privacy?"
        ),
    }
}


class LayaSpanAdvisor:
    """Span verification using laya's non-autoregressive Router.

    Each uncertain span is verified with a noul question in ~33 ms.
    Spans run concurrently via the thread-pool executor.
    No LLM API key required — runs entirely locally.
    """

    def __init__(self, router: Any, settings: "Settings", executor: ThreadPoolExecutor) -> None:
        self._router = router
        self._settings = settings
        self._executor = executor

    async def advise(self, text: str, entities: tuple[Entity, ...]) -> AdvisorResult:
        """Verify uncertain spans via laya; fail-open on any error.

        Trust-routed entities and high-score entities bypass verification, matching
        SpanAdvisor behaviour exactly.
        """
        s = self._settings
        certain: list[Entity] = []
        advisor_spans: list[Entity] = []

        for entity in entities:
            if entity.verification == "trust" or entity.score >= s.advisor_score_threshold:
                certain.append(entity)
            else:
                advisor_spans.append(entity)

        if not advisor_spans:
            return AdvisorResult(entities=tuple(certain), advisor_applied=False)

        kept, verified = await self._verify_spans(text, advisor_spans)
        merged = sorted(certain + kept, key=lambda e: e.start)
        return AdvisorResult(entities=tuple(merged), advisor_applied=verified)

    async def _verify_spans(
        self, text: str, spans: list[Entity]
    ) -> tuple[list[Entity], bool]:
        """Verify spans via laya; returns (kept_entities, all_verified).

        ``all_verified`` is False when any span fails verification (fail-open),
        matching SpanAdvisor's contract: advisor_applied=False on any error.
        """
        loop = asyncio.get_running_loop()
        any_failed = False

        async def _verify_one(entity: Entity) -> Entity | None:
            nonlocal any_failed
            s = self._settings
            context = text[
                max(0, entity.start - s.advisor_context_chars) : entity.end + s.advisor_context_chars
            ]
            state = {
                "entity_type": entity.entity_type.value,
                "span": entity.text,
                "context": context,
            }
            try:
                result = await loop.run_in_executor(
                    self._executor,
                    lambda: self._router.predict(state, _VERIFY_QUESTION),
                )
                prob: float = result["answers"]["is_genuine_pii"]["noul"]
                return entity if prob >= s.laya_pii_threshold else None
            except Exception:
                logger.exception(
                    "Laya span verification failed for span '%s'; keeping (fail-open)", entity.text
                )
                any_failed = True
                return entity  # fail-open

        tasks = [_verify_one(entity) for entity in spans]
        results = await asyncio.gather(*tasks)
        return [e for e in results if e is not None], not any_failed


def build_laya_advisor(settings: "Settings", executor: ThreadPoolExecutor) -> LayaSpanAdvisor:
    """Build a LayaSpanAdvisor from application settings.

    Raises ImportError if the laya extra is not installed.
    """
    from laya import Router  # noqa: PLC0415

    router = Router(preload=settings.laya_preload)
    logger.info("Laya span advisor loaded (preload=%s)", settings.laya_preload)
    return LayaSpanAdvisor(router=router, settings=settings, executor=executor)

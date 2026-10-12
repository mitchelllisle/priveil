"""Span judge — Type-1, non-autoregressive PII verification.

Uses noul (yes/no likelihood) questions to verify whether detected spans are
genuine PII. Current implementation: laya Router. Typical latency: ~33 ms per
span on CPU.

Requires: uv sync --extra laya
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel

from priveil.domain.entities import Entity

if TYPE_CHECKING:
    from priveil.settings import Settings

logger = logging.getLogger(__name__)


class JudgeResult(BaseModel, frozen=True):
    """Result of a span-verdict judge pass."""

    entities: tuple[Entity, ...]
    judge_applied: bool


class JudgeProtocol(Protocol):
    """Structural protocol for span judges (SpanJudge satisfies this)."""

    async def judge(self, text: str, entities: tuple[Entity, ...]) -> JudgeResult: ...

_VERIFY_QUESTION: dict[str, Any] = {
    "is_genuine_pii": {
        "type": "noul",
        "instructions": (
            "Is the detected span a genuine real-world PII entity of the stated type "
            "that should be redacted to protect someone's privacy?"
        ),
    }
}


class SpanJudge:
    """Span verification using a Type-1 non-autoregressive model (laya Router).

    Each uncertain span is verified with a noul question in ~33 ms.
    Spans run concurrently via the thread-pool executor.
    No LLM API key required — runs entirely locally.
    """

    def __init__(self, router: Any, settings: "Settings", executor: ThreadPoolExecutor) -> None:
        self._router = router
        self._settings = settings
        self._executor = executor

    async def judge(self, text: str, entities: tuple[Entity, ...]) -> JudgeResult:
        """Verify uncertain spans; fail-open on any error.

        Trust-routed entities and high-score entities bypass verification.
        """
        s = self._settings
        certain: list[Entity] = []
        judge_spans: list[Entity] = []

        for entity in entities:
            if entity.verification == "trust" or entity.score >= s.judge_score_threshold:
                certain.append(entity)
            else:
                judge_spans.append(entity)

        if not judge_spans:
            return JudgeResult(entities=tuple(certain), judge_applied=False)

        kept, verified = await self._verify_spans(text, judge_spans)
        merged = sorted(certain + kept, key=lambda e: e.start)
        return JudgeResult(entities=tuple(merged), judge_applied=verified)

    async def _verify_spans(
        self, text: str, spans: list[Entity]
    ) -> tuple[list[Entity], bool]:
        """Verify spans; returns (kept_entities, all_verified).

        ``all_verified`` is False when any span fails (fail-open):
        judge_applied=False on any error.
        """
        loop = asyncio.get_running_loop()
        any_failed = False

        async def _verify_one(entity: Entity) -> Entity | None:
            nonlocal any_failed
            s = self._settings
            context = text[
                max(0, entity.start - s.judge_context_chars) : entity.end + s.judge_context_chars
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
                return entity if prob >= s.judge_pii_threshold else None
            except Exception:
                logger.exception(
                    "Span judge verification failed for span '%s'; keeping (fail-open)", entity.text
                )
                any_failed = True
                return entity  # fail-open

        tasks = [_verify_one(entity) for entity in spans]
        results = await asyncio.gather(*tasks)
        return [e for e in results if e is not None], not any_failed


def build_span_judge(settings: "Settings", executor: ThreadPoolExecutor) -> SpanJudge:
    """Build a SpanJudge from application settings.

    Raises ImportError if the laya extra is not installed.
    """
    from laya import Router  # noqa: PLC0415

    router = Router(preload=settings.judge_preload)
    logger.info("Span judge loaded (preload=%s)", settings.judge_preload)
    return SpanJudge(router=router, settings=settings, executor=executor)

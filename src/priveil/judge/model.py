"""OpenAI client factory for the judge/refiner layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from priveil.settings import Settings


def build_judge_client(settings: "Settings") -> "AsyncOpenAI":
    """Build an AsyncOpenAI client for the span-verdict refiner."""
    from openai import AsyncOpenAI

    if settings.judge_base_url:
        api_key = settings.judge_api_key.get_secret_value() if settings.judge_api_key else "local"
        return AsyncOpenAI(base_url=settings.judge_base_url, api_key=api_key)

    if settings.judge_api_key:
        return AsyncOpenAI(api_key=settings.judge_api_key.get_secret_value())
    return AsyncOpenAI()

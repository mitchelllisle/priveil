"""Shared model/client factories for the advisor layer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from pydantic_ai.models.openai import OpenAIChatModel

    from priveil.settings import Settings

# pydantic-ai accepts str | Model for the agent's model parameter.
AdvisorModel = Union[str, "OpenAIChatModel"]


def build_advisor_model(settings: "Settings") -> AdvisorModel:
    """Return the appropriate pydantic-ai model for the advisor layer.

    Args:
        settings: Application settings.

    Returns:
        A provider:model string for built-in providers, or an OpenAIChatModel
        instance configured for a custom OpenAI-compatible endpoint.

    Raises:
        ValueError: If advisor_model is not set.
    """
    if not settings.advisor_model:
        raise ValueError(
            "PRIVEIL_ADVISOR_MODEL must be set. "
            "Use 'provider:model' format (e.g. 'anthropic:claude-sonnet-4-6') "
            "or a deployment name when PRIVEIL_ADVISOR_BASE_URL is configured."
        )

    if settings.advisor_base_url:
        model_name = settings.advisor_model
        assert model_name is not None  # validated at top of this function
        # Pass model name as-is — when base_url is set, the user configures the
        # name for that specific endpoint (e.g. "gemma4:e4b" for Ollama,
        # "google/gemma-4-E4B-it" for vLLM). No prefix stripping.
        api_key = settings.advisor_api_key.get_secret_value() if settings.advisor_api_key else "local"
        return _build_openai_compatible_model(
            model_name=model_name,
            base_url=settings.advisor_base_url,
            api_key=api_key,
        )

    # Built-in provider — pydantic-ai resolves "anthropic:...", "openai:...", etc.
    model_name = settings.advisor_model
    assert model_name is not None  # validated at top of this function
    return model_name


def _build_openai_compatible_model(model_name: str, base_url: str, api_key: str) -> "OpenAIChatModel":
    """Build an OpenAIChatModel for a custom OpenAI-compatible endpoint.

    Args:
        model_name: Validated deployment/model name.
        base_url: The endpoint base URL.
        api_key: Bearer token, already extracted from SecretStr by the caller.
    """
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    return OpenAIChatModel(
        model_name=model_name,
        provider=OpenAIProvider(openai_client=client),
    )

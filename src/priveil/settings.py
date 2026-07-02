
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All vars are prefixed with PRIVEIL_ (e.g. PRIVEIL_DEBUG=true).
    """

    model_config = SettingsConfigDict(
        env_prefix="PRIVEIL_",
        env_file=".env",
        extra="ignore",
    )

    debug: bool = False
    executor_max_workers: int = 4
    # ── GLiNER2 NER detector ──────────────────────────────────────────────────
    # Model for PERSON, LOCATION, DATE_TIME detection.
    # Requires: uv sync --extra gliner
    # When gliner2 is not installed, NER recognisers are skipped (regex-only mode).
    gliner2_model: str = "fastino/gliner2-base-v1"
    # ── LLM advisor ───────────────────────────────────────────────────────────
    # Set PRIVEIL_ADVISOR_MODEL to enable span-level advisor and /assess.
    # When unset: mode='advisor' falls back to 'fast'; /assess returns 503.
    # Ollama (local dev):  gemma4:e4b  at PRIVEIL_ADVISOR_BASE_URL=http://localhost:11434/v1
    # vLLM (production):   google/gemma-4-E4B-it  at PRIVEIL_ADVISOR_BASE_URL=http://vllm:8000/v1
    advisor_model: str | None = None
    advisor_temperature: float = 0.0
    # Custom OpenAI-compatible endpoint (vLLM, Ollama, etc.)
    advisor_base_url: str | None = None
    advisor_api_key: SecretStr | None = None
    # Entities scoring >= this are "certain" and bypass the advisor even when
    # their recogniser declares verification="advisor".
    advisor_score_threshold: float = 0.9
    advisor_context_chars: int = 60
    advisor_timeout_ms: int = 250
    advisor_max_tokens: int = 64
    # ── LLM judge ─────────────────────────────────────────────────────────────
    # Set PRIVEIL_JUDGE_MODEL to enable span-verdict refinement.
    # When unset: mode='judge' falls back to 'fast'.
    judge_model: str | None = None
    judge_temperature: float = 0.0
    # Custom OpenAI-compatible endpoint (e.g. local vLLM).
    # When set, judge_model is treated as the endpoint model/deployment name.
    judge_base_url: str | None = None
    judge_api_key: SecretStr | None = None
    judge_score_threshold: float = 0.85
    judge_eligible_types: frozenset[str] = frozenset({"PERSON", "LOCATION", "DATE_TIME", "AU_BSB", "AU_ACCOUNT_NUMBER"})
    judge_context_chars: int = 60
    judge_timeout_ms: int = 250
    judge_max_tokens: int = 64
    # Key used for HMAC audit hashes. Set this explicitly for stable hashes across
    # restarts and environments where audit correlation matters.
    audit_hash_key: SecretStr | None = None

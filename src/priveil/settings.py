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
    # Entities scoring >= this are "certain" and bypass the advisor even when
    # their recogniser declares verification="advisor".
    advisor_score_threshold: float = 0.9
    advisor_context_chars: int = 60
    # ── Laya span advisor ─────────────────────────────────────────────────────
    # Backend for mode='advisor' span verification: "auto" | "laya"
    # "auto" (default): uses laya if the package is installed.
    # "laya" requires laya package (uv sync --extra laya).
    advisor_backend: str = "auto"
    # Probability threshold for laya noul answer — spans scoring >= this are kept.
    laya_pii_threshold: float = 0.5
    # Preload laya checkpoints at startup (vs lazy on first request). Set True in production.
    laya_preload: bool = False
    # ── Laya assessor ─────────────────────────────────────────────────────────
    # Backend for /assess: "auto" | "laya"
    # "auto" (default): uses laya if installed, else 503.
    # "laya" requires laya package and returns rule-derived fields (no text generation).
    assess_backend: str = "auto"
    # Key used for HMAC audit hashes. Set this explicitly for stable hashes across
    # restarts and environments where audit correlation matters.
    audit_hash_key: SecretStr | None = None

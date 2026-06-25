from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All vars are prefixed with ALIAS_ (e.g. ALIAS_DEBUG=true).
    """

    model_config = SettingsConfigDict(
        env_prefix="ALIAS_",
        env_file=".env",
        extra="ignore",
    )

    debug: bool = False

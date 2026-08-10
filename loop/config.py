"""Central configuration, loaded from the environment / `.env`.

Every tunable in the README's Configuration table lives here so the rest of the
codebase never reads `os.environ` directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database ---
    postgres_dsn: str = Field(
        default="postgresql+psycopg://loop:change-me@localhost:5432/loop",
        alias="POSTGRES_DSN",
    )

    # --- Redis / Celery ---
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- LLM backend ---
    # anthropic | gemini
    llm_backend: str = Field(default="anthropic", alias="LLM_BACKEND")

    # Anthropic
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    llm_model_small: str = Field(default="claude-haiku-4-5", alias="LLM_MODEL_SMALL")
    llm_model_large: str = Field(default="claude-sonnet-5", alias="LLM_MODEL_LARGE")

    # Gemini. `gemini-flash-latest` is a stable alias that resolves to the
    # current recommended free-tier flash model — more robust than pinning a
    # version, some of which are gated off for newly-created API keys.
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model_small: str = Field(
        default="gemini-flash-latest", alias="GEMINI_MODEL_SMALL"
    )
    gemini_model_large: str = Field(
        default="gemini-flash-latest", alias="GEMINI_MODEL_LARGE"
    )

    # --- Embeddings ---
    embed_model: str = Field(default="BAAI/bge-small-en-v1.5", alias="EMBED_MODEL")
    embed_dim: int = 384  # bge-small-en-v1.5

    # --- Clustering ---
    cluster_threshold: float = Field(default=0.75, alias="CLUSTER_THRESHOLD")
    cluster_active_days: int = Field(default=7, alias="CLUSTER_ACTIVE_DAYS")

    # --- Synthesis gating ---
    freshness_gate_hours: int = Field(default=2, alias="FRESHNESS_GATE_HOURS")
    min_sources_for_synthesis: int = Field(
        default=3, alias="MIN_SOURCES_FOR_SYNTHESIS"
    )
    importance_threshold_large_model: float = Field(
        default=0.7, alias="IMPORTANCE_THRESHOLD_LARGE_MODEL"
    )

    # --- Ranking / personalisation ---
    personalization_lambda: float = Field(default=0.3, alias="PERSONALIZATION_LAMBDA")
    seen_penalty: float = Field(default=0.5, alias="SEEN_PENALTY")

    # --- Retention (copyright compliance) ---
    body_retention_hours: int = Field(default=72, alias="BODY_RETENTION_HOURS")

    # --- Ingestion ---
    fetch_interval_minutes: int = Field(default=5, alias="FETCH_INTERVAL_MINUTES")
    fetch_max_concurrency: int = Field(default=8, alias="FETCH_MAX_CONCURRENCY")
    user_agent: str = Field(
        default="LoopNewsBot/0.1 (+https://github.com/you/loop)", alias="USER_AGENT"
    )

    # --- App ---
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Convenience singleton for import-site use.
settings = get_settings()

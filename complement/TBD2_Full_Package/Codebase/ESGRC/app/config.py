"""
Application settings using pydantic-settings v2.

The @lru_cache pattern ensures Settings() is instantiated exactly once per
process - the .env file is read on first call and cached for all subsequent
imports.  Tests can override by calling get_settings.cache_clear() before
patching environment variables.
"""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    APP_NAME: str = "ESGRC API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database - override with postgresql+psycopg:// in production
    DATABASE_URL: str = "sqlite:///./esgrc.db"
    # Connection pool settings - only used for non-SQLite databases (Postgres, etc.)
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # CORS - comma-separated explicit origins, e.g.
    # "https://app.example.com,https://admin.example.com"
    # Leave empty ("") to allow all origins in dev mode (credentials disabled).
    ALLOWED_ORIGINS: str = ""

    # ── Authentication / JWT ──────────────────────────────────────────────────
    # SECRET_KEY: used to sign JWT tokens.
    # Generate a strong key with: python -c "import secrets; print(secrets.token_hex(32))"
    # NEVER use the default in production - set via environment variable.
    SECRET_KEY: str = "change-me-in-production-use-secrets-token-hex-32"
    # Algorithm for JWT signing. HS256 is standard; use RS256 for asymmetric keys.
    JWT_ALGORITHM: str = "HS256"
    # Access token lifetime in minutes (short-lived - 30 min is a safe default).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # Refresh token lifetime in days (long-lived - used to issue new access tokens).
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Agent / Scheduler ─────────────────────────────────────────────────────
    # Cron schedule for the daily batch agent.
    # AGENT_HOUR / AGENT_MINUTE: when to run each day (UTC).
    # Default: 02:00 UTC (quiet window for most organisations).
    AGENT_HOUR: int = 2
    AGENT_MINUTE: int = 0
    # AGENT_TIMEZONE: timezone for cron scheduling.
    AGENT_TIMEZONE: str = "UTC"
    # Enable/disable the agent entirely (set false in test environments).
    AGENT_ENABLED: bool = True
    # How many days between compliance requirement re-checks.
    # Praveen's recommendation: 15 days is the right cadence for compliance
    # reviews - daily is too noisy, monthly is too slow.
    COMPLIANCE_CHECK_DAYS: int = 15

    # ── LLM Agent ─────────────────────────────────────────────────────────────
    # Anthropic API key for the LLM agent layer.
    # Get from https://console.anthropic.com
    # NEVER commit a real key - always load from environment variable.
    ANTHROPIC_API_KEY: str = ""
    # Orchestrator model - reads all data, reasons, and delegates.
    # claude-sonnet-5 is the current active Sonnet (verified against Anthropic's
    # own model catalog); claude-sonnet-4-6 still works but is no longer the
    # recommended choice, and the old dated claude-sonnet-4-20250514 is
    # deprecated/retiring - matches .env.example.
    ORCHESTRATOR_MODEL: str = "claude-sonnet-5"
    # Specialist model - cheaper, faster for focused classification tasks.
    SPECIALIST_MODEL: str = "claude-haiku-4-5-20251001"
    # Max tokens the orchestrator can use per run (4096 is sufficient for batch work).
    ORCHESTRATOR_MAX_TOKENS: int = 4096
    # Whether to run the LLM agent (set false to use rule-based batch only).
    LLM_AGENT_ENABLED: bool = False  # safe default - requires API key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    s = Settings()
    logger.debug("Settings loaded: app=%s debug=%s", s.APP_NAME, s.DEBUG)
    return s


settings: Settings = get_settings()

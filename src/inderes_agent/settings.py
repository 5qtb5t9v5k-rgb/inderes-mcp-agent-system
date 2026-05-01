"""Settings, loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    GEMINI_API_KEY: str = Field(default="", description="Google AI Studio API key")

    INDERES_MCP_URL: str = "https://mcp.inderes.com"
    INDERES_MCP_CLIENT_ID: str = "inderes-mcp"

    PRIMARY_MODEL: str = "gemini-3.1-flash-lite-preview"
    FALLBACK_MODEL: str = "gemini-2.5-flash"

    RETRY_DELAY_MS: int = 1000
    MAX_RETRIES: int = 1

    MAX_CONCURRENT_AGENTS: int = 2

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    def require_gemini_key(self) -> str:
        if not self.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com and "
                "add it to .env"
            )
        return self.GEMINI_API_KEY


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

"""Application settings loaded from environment variables.

Uses pydantic-settings to read from the parent .env file.
All settings have sensible defaults so the app starts with just GEMINI_API_KEY set.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve paths:
#   this file:    .../marketing agent v2/app/config.py
#   _V2_DIR:      .../marketing agent v2/
#   _PROJECT_ROOT: .../multi-agent marketing system/   (where .env lives)
_V2_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _V2_DIR.parent


class Settings(BaseSettings):
    """Central configuration — one source of truth for the whole app."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",  # silently skip V1 keys like OPENAI_API_KEY
    )

    # ── API Keys ──────────────────────────────────────────────────────────
    gemini_api_key: str = ""

    # ── LLM Settings ─────────────────────────────────────────────────────
    gemini_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.3
    llm_max_output_tokens: int = 4096

    # ── Scraping Defaults ────────────────────────────────────────────────
    scrape_max_pages: int = 5
    scrape_timeout_seconds: int = 30
    scrape_delay_seconds: float = 1.0
    scrape_max_page_size_kb: int = 5120
    scrape_user_agent: str = (
        "MarketingResearchBot/1.0 (+https://github.com/your-repo; research purposes)"
    )

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = ""

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "Marketing Agent V2"
    app_version: str = "0.1.0"
    debug: bool = False

    @property
    def effective_database_url(self) -> str:
        """Return the configured DB URL, or a default SQLite path under data/."""
        if self.database_url:
            return self.database_url
        db_path = _V2_DIR / "data" / "marketing_v2.db"
        return f"sqlite+aiosqlite:///{db_path}"


# Module-level singleton — import this everywhere.
# Created once on first import, reads .env at that point.
settings = Settings()

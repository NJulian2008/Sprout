"""
Application settings for Sprout, loaded via pydantic-settings.

All fields have sensible defaults so the app starts without a ``.env`` file
present (useful for tests and fresh checkouts).  In production, override
values by creating a ``.env`` file or by setting environment variables
directly.

Usage::

    from app.settings import settings

    print(settings.database_url)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object.

    Fields
    ------
    database_url:
        SQLAlchemy connection string.  Defaults to a local SQLite file.
    session_secret:
        Secret key used to sign session cookies.  Must be changed in
        production.
    llm_mode:
        Controls AI/LLM behaviour.  One of ``"live"``, ``"off"``, or
        ``"cached"``.
    demo_mode:
        Controls demo-panel behaviour.  One of ``"normal"`` or ``"off"``.
    copilot_token:
        Bearer token for the GitHub Copilot (or compatible) LLM endpoint.
        Leave empty when ``llm_mode`` is not ``"live"``.
    """

    database_url: str = "sqlite:///app.db"
    session_secret: str = "change-me-in-production"
    llm_mode: str = "off"  # "live" | "off" | "cached"
    demo_mode: str = "normal"  # "normal" | "off"
    copilot_token: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Module-level singleton used throughout the application.
settings = Settings()

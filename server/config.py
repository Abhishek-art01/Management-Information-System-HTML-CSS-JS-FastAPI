"""
config.py — single source of truth for all environment settings.
All modules import from here, never from os.environ directly.
"""
from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_title: str = "Management Information System"
    app_version: str = "2.0.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False

    # Security
    secret_key: str = "CHANGE_ME"
    session_max_age: int = 3600

    # Database
    database_url: str = "sqlite:///./mis.db"

    # CORS  (comma-separated string → list)
    cors_origins: str = "http://localhost:8000"

    # Pagination
    default_page_size: int = 20
    max_page_size: int = 100

    # Company
    company_name: str = "T3 Logistics"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.database_url

    @property
    def is_render(self) -> bool:
        import os
        return os.environ.get("RENDER") is not None


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — import this everywhere."""
    return Settings()

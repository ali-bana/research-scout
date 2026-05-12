from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_secret_key: str = ""
    admin_password_hash: str = ""
    session_https_only: bool = False
    public_base_url: str = "http://127.0.0.1:8000"

    database_url: str = "sqlite:///./data/research_radar.db"
    profile_path: str = "config/profile.yaml"
    rss_feeds_path: str = "config/rss_feeds.yaml"

    arxiv_categories: str = "cs.AI,cs.CL,cs.LG,cs.CV,stat.ML"
    arxiv_max_results: int = 75
    arxiv_days_back: int = 14
    http_timeout_seconds: float = 25.0

    daily_max_papers: int = 10
    weekly_discovery_window_days: int = 180

    notion_token: str = ""
    notion_page_ids: str = ""
    notion_database_id: str = ""

    semantic_scholar_api_key: str = ""
    openalex_email: str = ""
    openalex_api_key: str = ""
    openalex_token: str = ""

    x_api_key: str = ""
    x_bearer_token: str = ""
    x_list_ids: str = ""

    llm_provider: str = "mock"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    openai_base_url: str = "http://127.0.0.1:8001/v1"
    openai_api_key: str = ""
    openai_model: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    digest_to_email: str = ""

    log_level: str = Field(default="INFO")

    @property
    def arxiv_category_list(self) -> list[str]:
        return split_csv(self.arxiv_categories)

    @property
    def notion_page_id_list(self) -> list[str]:
        return split_csv(self.notion_page_ids)

    @property
    def x_list_id_list(self) -> list[str]:
        return split_csv(self.x_list_ids)

    def path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

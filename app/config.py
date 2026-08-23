from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
CONFIGS_DIR = BASE_DIR / "configs"
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
GOLDEN_DATA_DIR = DATA_DIR / "golden"
STATIC_DIR = BASE_DIR / "static"

# Ensure essential directories exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
GOLDEN_DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Application global settings."""
    app_name: str = "AI Lead Intelligence & Crawler"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, validation_alias="APP_DEBUG")
    environment: str = "development"

    # Server binding
    host: str = "127.0.0.1"
    port: int = 8000

    # Database
    database_url: str = f"sqlite:///{BASE_DIR / 'leads.db'}"

    # AI Model & Extraction & Scoring
    ai_provider: str = Field(default="gemini", description="gemini, openai, or rule_based")
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash-lite"
    gemini_base_url: str | None = None  # Custom OpenAI-compatible proxy or gateway URL
    ai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    llm_timeout_seconds: int = 45

    # XAH Search API - credentials always stay on the backend
    xah_api_key: str | None = None
    xah_search_url: str = "https://api.xah.io/v1/search"
    xah_search_model: str = "search"
    xah_search_type: str = "web"
    xah_max_results: int = 5
    xah_country: str = "Vietnam"
    xah_language: str = "Vietnam"
    xah_timeout_seconds: int = 60

    # Google Sheets durable database (SQLite is only a local query cache)
    google_sheets_spreadsheet_id: str | None = None
    google_service_account_json: str | None = None
    google_sheets_leads_worksheet: str = "Leads"
    google_sheets_settings_worksheet: str = "Settings"

    # Scheduler defaults (Vietnam local time)
    scheduler_enabled: bool = True
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"
    scheduler_hour: int = 6
    scheduler_minute: int = 0

    # Crawler Settings
    crawler_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 AILeadCrawler/1.0"
    )
    crawl_timeout_seconds: int = 30
    max_retries: int = 2
    retry_backoff_factor: float = 1.5
    default_rate_limit_delay: float = 1.0

    # Security
    secret_key: str = Field(default="ai-lead-intelligence-secure-key-2026", description="Secret key for sessions/tokens")
    allowed_origins: List[str] = ["http://127.0.0.1:8000", "http://localhost:8000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def load_yaml_config(file_path: Path) -> Dict[str, Any]:
    """Safely loads a YAML configuration file."""
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_sources_config() -> Dict[str, Any]:
    return load_yaml_config(CONFIGS_DIR / "sources.yaml")


def get_keywords_config() -> Dict[str, Any]:
    return load_yaml_config(CONFIGS_DIR / "keywords.yaml")


def get_scoring_config() -> Dict[str, Any]:
    return load_yaml_config(CONFIGS_DIR / "scoring.yaml")

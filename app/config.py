from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List
import yaml
from pydantic import Field, model_validator
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
    ai_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "levuphong2909/gemini-3.8-flash-high"
    gemini_base_url: str | None = None  # Custom OpenAI-compatible proxy or gateway URL
    ai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "dungcsnd113/deepseek-v4-flash-0731"
    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    llm_timeout_seconds: int = 60

    # XAH Search API - credentials always stay on the backend
    xah_api_key: str | None = None
    xah_search_url: str = "https://api.xah.io/v1/search"
    xah_search_model: str = "dungcsnd113/deepseek-v4-flash-0731"
    xah_search_type: str = "web"
    xah_max_results: int = 5
    xah_country: str = "Vietnam"
    xah_language: str = "Vietnam"
    xah_timeout_seconds: int = 60

    @model_validator(mode="after")
    def _normalize_ai_settings(self) -> Settings:
        # Fallback API key: ai_api_key <-> xah_api_key <-> gemini_api_key <-> openai_api_key
        common_key = self.xah_api_key or self.ai_api_key or self.gemini_api_key or self.openai_api_key
        if not self.xah_api_key and common_key:
            self.xah_api_key = common_key
        if not self.gemini_api_key and common_key:
            self.gemini_api_key = common_key
        if not self.openai_api_key and common_key:
            self.openai_api_key = common_key
        if not self.ai_api_key and common_key:
            self.ai_api_key = common_key

        # Normalization and fallback for base URLs:
        common_base = self.ai_base_url or self.gemini_base_url or self.openai_base_url
        if common_base:
            clean_base = common_base.removesuffix("/chat/completions").rstrip("/")
            if not self.ai_base_url:
                self.ai_base_url = clean_base
            if not self.gemini_base_url:
                self.gemini_base_url = clean_base
            else:
                self.gemini_base_url = self.gemini_base_url.removesuffix("/chat/completions").rstrip("/")
            if not self.openai_base_url:
                self.openai_base_url = clean_base
            else:
                self.openai_base_url = self.openai_base_url.removesuffix("/chat/completions").rstrip("/")
        return self

    # Apify LinkedIn Post Search; token stays on the backend.
    apify_api_token: str | None = None
    apify_linkedin_actor_id: str = "harvestapi/linkedin-post-search"
    apify_linkedin_max_posts_per_keyword: int = 1000
    apify_linkedin_profile_scraper_mode: str = "short"
    apify_linkedin_content_type: str = "jobs"
    apify_linkedin_sort_by: str = "relevance"
    apify_linkedin_run_timeout_seconds: int = 9000

    # Round-two organization enrichment: crawl a verified round-one URL when
    # available; otherwise Gemini creates keywords and XAH returns sourced web
    # content directly. XAH also fills evidence gaps after a direct crawl.
    company_enrichment_enabled: bool = True
    company_enrichment_mode: str = "xah"
    company_profile_max_pages: int = 20
    company_profile_max_depth: int = 3
    company_xah_max_queries: int = 3
    # Retry XAH URL discovery when all returned URLs fail backend crawling.
    # The service caps this value at 5 attempts.
    company_xah_retry_attempts: int = 5

    # Google Sheets durable database (SQLite is only a local query cache)
    google_sheets_spreadsheet_id: str | None = None
    google_service_account_json: str | None = None
    google_sheets_leads_worksheet: str = "Leads"
    google_sheets_settings_worksheet: str = "Settings"
    google_sheets_keywords_worksheet: str = "Keywords"
    google_sheets_sources_worksheet: str = "Sources"
    google_sheets_organizations_worksheet: str = "Organizations"
    google_sheets_contacts_worksheet: str = "Contacts"
    google_sheets_evidence_worksheet: str = "Organization_Evidence"
    google_sheets_projects_worksheet: str = "Projects"
    google_sheets_news_worksheet: str = "News"
    google_sheets_jobs_worksheet: str = "Jobs"
    google_sheets_tenders_worksheet: str = "Tenders"
    google_sheets_interactions_worksheet: str = "Interactions"

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
    crawl_timeout_seconds: int = 60
    max_retries: int = 2
    retry_backoff_factor: float = 1.5
    default_rate_limit_delay: float = 1.0

    # Optional residential proxy for anti-bot protected TopCV pages.
    topcv_proxy_url: str | None = None

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

"""Google Sheets-backed runtime settings for the LinkedIn Apify source."""

from __future__ import annotations

import threading
from typing import Any

from app.config import settings
from app.pipeline.normalize import utc_now
from app.services.google_sheets_service import google_sheets_service
from app.services.setting_service import setting_service


LINKEDIN_APIFY_SETTING_KEY = "linkedin_apify_config"
MIN_POSTS_PER_KEYWORD = 1
MAX_POSTS_PER_KEYWORD = 1000


class LinkedInSettingsService:
    def __init__(self, sheets=None) -> None:
        self.sheets = sheets if sheets is not None else setting_service
        self._lock = threading.RLock()
        self._cached_max_posts: int | None = None

    @staticmethod
    def _validate(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Số bài mỗi keyword phải là số nguyên") from exc
        if not MIN_POSTS_PER_KEYWORD <= parsed <= MAX_POSTS_PER_KEYWORD:
            raise ValueError(
                f"Số bài mỗi keyword phải từ {MIN_POSTS_PER_KEYWORD} đến "
                f"{MAX_POSTS_PER_KEYWORD}"
            )
        return parsed

    def get_config(self, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._cached_max_posts is not None and not refresh:
                value = self._cached_max_posts
            else:
                stored = self.sheets.load_setting(LINKEDIN_APIFY_SETTING_KEY)
                stored_value = (
                    stored.get("max_posts_per_keyword")
                    if isinstance(stored, dict)
                    else None
                )
                try:
                    value = self._validate(stored_value)
                except ValueError:
                    value = self._validate(
                        settings.apify_linkedin_max_posts_per_keyword
                    )
                self._cached_max_posts = value

                if stored_value is None:
                    if not hasattr(self.sheets, "configured") or self.sheets.configured:
                        self.sheets.save_setting(
                            LINKEDIN_APIFY_SETTING_KEY,
                            {
                                "max_posts_per_keyword": value,
                                "updated_at": utc_now().isoformat(),
                            },
                        )

        return {
            "max_posts_per_keyword": value,
            "min_posts_per_keyword": MIN_POSTS_PER_KEYWORD,
            "max_allowed_posts_per_keyword": MAX_POSTS_PER_KEYWORD,
            "setting_key": LINKEDIN_APIFY_SETTING_KEY,
            "storage": "sqlite" if self.sheets is setting_service else ("google_sheets" if getattr(self.sheets, "configured", False) else "environment"),
        }

    def update(self, max_posts_per_keyword: int) -> dict[str, Any]:
        value = self._validate(max_posts_per_keyword)
        if hasattr(self.sheets, "configured") and not self.sheets.configured:
            raise RuntimeError(
                "Kho lưu trữ chưa được cấu hình để lưu thiết lập LinkedIn"
            )
        res = self.sheets.save_setting(
            LINKEDIN_APIFY_SETTING_KEY,
            {
                "max_posts_per_keyword": value,
                "updated_at": utc_now().isoformat(),
            },
        )
        if res is False:
            raise RuntimeError(
                getattr(self.sheets, "last_error", None)
                or "Không thể lưu thiết lập LinkedIn vào cơ sở dữ liệu"
            )
        with self._lock:
            self._cached_max_posts = value
        return self.get_config()


linkedin_settings_service = LinkedInSettingsService()

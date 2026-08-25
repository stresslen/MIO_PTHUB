from __future__ import annotations

import datetime
import re
import threading
import unicodedata
from typing import Any

from app.config import get_keywords_config

CUSTOM_GROUP_ID = "custom"
CUSTOM_GROUP_NAME = "Từ khóa tùy chỉnh"
MAX_IMPORT_KEYWORDS = 1000
MAX_KEYWORD_LENGTH = 160
MAX_DISCOVERY_KEYWORDS = 20


class KeywordValidationError(ValueError):
    pass


def _normalize_keyword_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"true", "1", "yes", "y", "có", "x"}


def parse_keyword_input(content: str) -> list[str]:
    """Parse comma, semicolon and line-delimited text with stable de-duplication."""
    if not isinstance(content, str) or not content.strip():
        raise KeywordValidationError("Nội dung keyword đang trống")
    values: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;\r\n]+", content):
        keyword = _normalize_keyword_text(raw)
        if not keyword:
            continue
        if len(keyword) > MAX_KEYWORD_LENGTH:
            raise KeywordValidationError(
                f"Keyword vượt quá {MAX_KEYWORD_LENGTH} ký tự: {keyword[:40]}…"
            )
        key = keyword.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(keyword)
        if len(values) > MAX_IMPORT_KEYWORDS:
            raise KeywordValidationError(
                f"Mỗi lần chỉ được thêm tối đa {MAX_IMPORT_KEYWORDS} keyword"
            )
    if not values:
        raise KeywordValidationError("Không tìm thấy keyword hợp lệ")
    return values


class KeywordService:
    """Google Sheets-backed keyword registry with an in-memory crawl cache."""

    def __init__(self, sheets_service=None) -> None:
        self._sheets = sheets_service
        self._lock = threading.RLock()
        self._seed_config = get_keywords_config()
        self._rows = self._build_seed_rows(self._seed_config)
        self._source = "yaml_bootstrap"
        self._last_error: str | None = None
        self._last_synced_at: str | None = None

    @property
    def sheets(self):
        if self._sheets is None:
            from app.services.google_sheets_service import google_sheets_service
            self._sheets = google_sheets_service
        return self._sheets

    @staticmethod
    def _build_seed_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        merged: dict[str, dict[str, Any]] = {}

        # Keep the curated discovery order first because crawlers consume it in order.
        for raw in config.get("discovery_search", {}).get("keywords", []):
            keyword = _normalize_keyword_text(raw)
            if not keyword:
                continue
            merged[keyword.casefold()] = {
                "keyword": keyword,
                "group_id": CUSTOM_GROUP_ID,
                "group_name": CUSTOM_GROUP_NAME,
                "use_for_filter": False,
                "use_for_discovery": True,
                "active": True,
                "created_at": now,
                "updated_at": now,
            }

        for group_id, group in config.get("keyword_groups", {}).items():
            for raw in group.get("keywords", []):
                keyword = _normalize_keyword_text(raw)
                if not keyword:
                    continue
                key = keyword.casefold()
                if key in merged:
                    merged[key].update(
                        group_id=group_id,
                        group_name=group.get("name") or group_id,
                        use_for_filter=True,
                    )
                    continue
                merged[key] = {
                    "keyword": keyword,
                    "group_id": group_id,
                    "group_name": group.get("name") or group_id,
                    "use_for_filter": True,
                    "use_for_discovery": False,
                    "active": True,
                    "created_at": now,
                    "updated_at": now,
                }
        return list(merged.values())

    @staticmethod
    def _clean_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in rows:
            keyword = _normalize_keyword_text(str(record.get("keyword") or ""))
            key = keyword.casefold()
            if not keyword or key in seen or not _as_bool(record.get("active"), True):
                continue
            seen.add(key)
            cleaned.append({
                "keyword": keyword,
                "group_id": _normalize_keyword_text(str(record.get("group_id") or CUSTOM_GROUP_ID)),
                "group_name": _normalize_keyword_text(str(record.get("group_name") or CUSTOM_GROUP_NAME)),
                "use_for_filter": _as_bool(record.get("use_for_filter"), True),
                "use_for_discovery": _as_bool(record.get("use_for_discovery"), False),
                "active": True,
                "created_at": str(record.get("created_at") or ""),
                "updated_at": str(record.get("updated_at") or ""),
            })
        return cleaned

    def bootstrap(self) -> dict[str, Any]:
        """Create/seed the worksheet once, then make it the runtime source."""
        if not self.sheets.configured:
            return self.snapshot()
        try:
            self.sheets.seed_keyword_rows(self._rows)
            return self.refresh()
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            raise

    def refresh(self) -> dict[str, Any]:
        if not self.sheets.configured:
            raise RuntimeError("Google Sheets chưa được cấu hình để đồng bộ keyword")
        rows = self._clean_rows(self.sheets.get_keyword_rows())
        if not rows:
            raise RuntimeError("Worksheet Keywords không có keyword đang hoạt động")
        with self._lock:
            self._rows = rows
            self._source = "google_sheets"
            self._last_error = None
            self._last_synced_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return self.snapshot()

    def add(self, content: str, use_for_discovery: bool = False) -> dict[str, Any]:
        if not self.sheets.configured:
            raise RuntimeError("Google Sheets chưa được cấu hình để lưu keyword")
        keywords = parse_keyword_input(content)
        with self._lock:
            discovery_keys = {
                row["keyword"].casefold()
                for row in self._rows
                if row["use_for_discovery"]
            }
        if use_for_discovery:
            requested = {value.casefold() for value in keywords}
            if len(discovery_keys | requested) > MAX_DISCOVERY_KEYWORDS:
                raise KeywordValidationError(
                    f"Search trực tiếp chỉ hỗ trợ tối đa {MAX_DISCOVERY_KEYWORDS} keyword để kiểm soát số request"
                )
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rows = [{
            "keyword": keyword,
            "group_id": CUSTOM_GROUP_ID,
            "group_name": CUSTOM_GROUP_NAME,
            "use_for_filter": True,
            "use_for_discovery": use_for_discovery,
            "active": True,
            "created_at": now,
            "updated_at": now,
        } for keyword in keywords]
        result = self.sheets.upsert_keyword_rows(rows)
        snapshot = self.refresh()
        return {**result, "submitted": len(keywords), "total": snapshot["total"]}

    def get_config(self) -> dict[str, Any]:
        with self._lock:
            rows = [dict(row) for row in self._rows]
        groups: dict[str, dict[str, Any]] = {}
        discovery: list[str] = []
        for row in rows:
            if row["use_for_filter"]:
                group = groups.setdefault(
                    row["group_id"],
                    {"name": row["group_name"], "keywords": []},
                )
                group["keywords"].append(row["keyword"])
            if row["use_for_discovery"]:
                discovery.append(row["keyword"])
        return {
            "keyword_groups": groups,
            "discovery_search": {
                "max_queries": min(MAX_DISCOVERY_KEYWORDS, len(discovery)),
                "keywords": discovery,
            },
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = [dict(row) for row in self._rows]
            source = self._source
            last_error = self._last_error
            last_synced_at = self._last_synced_at
        return {
            "items": items,
            "total": len(items),
            "filter_total": sum(1 for row in items if row["use_for_filter"]),
            "discovery_total": sum(1 for row in items if row["use_for_discovery"]),
            "source": source,
            "last_synced_at": last_synced_at,
            "last_error": last_error,
        }


keyword_service = KeywordService()

from __future__ import annotations

import datetime
import hashlib
import ipaddress
import json
import logging
import re
import socket
import threading
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.config import get_sources_config, settings
from app.database import SessionLocal
from app.models.source import CrawlerSourceItem
from app.pipeline.normalize import clean_html
from app.services.browser_crawl_service import browser_crawl_service
from app.services.priority_service import priority_coordinator

logger = logging.getLogger(__name__)

CUSTOM_MAX_PAGES = 200
CUSTOM_MAX_DEPTH = 3
ERROR_NOTICE = "Nguồn này chưa crawl được, cần cập nhật adapter sau."


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"true", "1", "yes", "y", "có", "x"}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def normalize_source_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if not host:
        return value
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), host + port, path, "", parsed.query, ""))


def validate_public_url(url: str, resolve_dns: bool = True) -> tuple[bool, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "Chỉ hỗ trợ URL HTTP hoặc HTTPS"
    if parsed.username or parsed.password:
        return False, "URL không được chứa username hoặc password"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "URL thiếu domain"
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False, "Không cho phép địa chỉ nội bộ"
    try:
        ip = ipaddress.ip_address(host)
        addresses = [ip]
    except ValueError:
        addresses = []
        if resolve_dns:
            try:
                addresses = {
                    ipaddress.ip_address(item[4][0])
                    for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
                }
            except OSError:
                return False, "Không phân giải được domain"
    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False, "Không cho phép địa chỉ mạng nội bộ hoặc dành riêng"
    return True, None


class SourceService:
    """Google Sheets-backed source registry with an in-memory crawl cache."""

    def __init__(self, sheets_service=None) -> None:
        self._sheets = sheets_service
        self._lock = threading.RLock()
        self._rows = self._build_seed_rows(get_sources_config())
        self._source = "yaml_bootstrap"
        self._last_synced_at: str | None = None
        self._last_error: str | None = None

    @property
    def sheets(self):
        if self._sheets is None:
            from app.services.google_sheets_service import google_sheets_service
            self._sheets = google_sheets_service
        return self._sheets

    @staticmethod
    def _build_seed_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
        now = _now()
        rows: list[dict[str, Any]] = []
        for item in config.get("sources", []):
            source_id = str(item.get("id") or "").strip()
            if not source_id:
                continue
            rows.append({
                "id": source_id,
                "name": str(item.get("name") or source_id),
                "description": str(item.get("description") or ""),
                "seed_urls": [
                    normalize_source_url(value)
                    for value in item.get("seed_urls", [])
                    if normalize_source_url(value)
                ],
                "adapter_mode": "specialized",
                "adapter_key": source_id,
                "crawl_scope": "configured",
                "rate_limit_delay": float(item.get("rate_limit_delay") or 1.0),
                "timeout": int(item.get("timeout") or 30),
                "enabled": _as_bool(item.get("enabled"), True),
                "include_in_schedule": _as_bool(item.get("enabled"), True),
                "status": "READY",
                "last_error": "",
                "last_attempt_at": "",
                "last_success_at": "",
                "created_at": now,
                "updated_at": now,
            })
        return rows

    @staticmethod
    def _clean_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in records:
            source_id = str(record.get("id") or "").strip()
            if not source_id or source_id in seen:
                continue
            raw_urls = record.get("seed_urls")
            if isinstance(raw_urls, str):
                try:
                    raw_urls = json.loads(raw_urls or "[]")
                except json.JSONDecodeError:
                    raw_urls = [raw_urls]
            urls = [
                normalize_source_url(value)
                for value in (raw_urls or [])
                if normalize_source_url(value)
            ]
            if not urls:
                continue
            seen.add(source_id)
            rows.append({
                "id": source_id,
                "name": str(record.get("name") or source_id).strip(),
                "description": str(record.get("description") or "").strip(),
                "seed_urls": urls,
                "adapter_mode": str(record.get("adapter_mode") or "generic").strip(),
                "adapter_key": str(record.get("adapter_key") or "generic").strip(),
                "crawl_scope": str(record.get("crawl_scope") or "full_site").strip(),
                "rate_limit_delay": float(record.get("rate_limit_delay") or 1.0),
                "timeout": int(float(record.get("timeout") or 30)),
                "enabled": _as_bool(record.get("enabled"), True),
                "include_in_schedule": _as_bool(record.get("include_in_schedule"), False),
                "status": str(record.get("status") or "NEW").strip(),
                "last_error": str(record.get("last_error") or "").strip(),
                "last_attempt_at": str(record.get("last_attempt_at") or "").strip(),
                "last_success_at": str(record.get("last_success_at") or "").strip(),
                "created_at": str(record.get("created_at") or ""),
                "updated_at": str(record.get("updated_at") or ""),
            })
        return rows

    @staticmethod
    def _load_from_sqlite() -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            items = session.query(CrawlerSourceItem).all()
            rows = []
            for item in items:
                rows.append({
                    "id": item.id,
                    "name": item.name,
                    "description": item.description or "",
                    "seed_urls": item.seed_urls if isinstance(item.seed_urls, list) else [],
                    "adapter_mode": item.adapter_mode or "specialized",
                    "adapter_key": item.adapter_key or item.id,
                    "crawl_scope": item.crawl_scope or "configured",
                    "rate_limit_delay": float(item.rate_limit_delay or 1.0),
                    "timeout": int(item.timeout or 30),
                    "enabled": bool(item.enabled),
                    "include_in_schedule": bool(item.include_in_schedule),
                    "status": item.status or "READY",
                    "last_error": item.last_error or "",
                    "last_attempt_at": item.last_attempt_at or "",
                    "last_success_at": item.last_success_at or "",
                    "created_at": item.created_at or "",
                    "updated_at": item.updated_at or "",
                })
            return rows
        finally:
            session.close()

    @staticmethod
    def _seed_sqlite(rows: list[dict[str, Any]]) -> None:
        session = SessionLocal()
        try:
            count = session.query(CrawlerSourceItem).count()
            if count == 0:
                for r in rows:
                    item = CrawlerSourceItem(
                        id=r["id"],
                        name=r.get("name") or r["id"],
                        description=r.get("description") or "",
                        seed_urls=r.get("seed_urls") or [],
                        adapter_mode=r.get("adapter_mode") or "specialized",
                        adapter_key=r.get("adapter_key") or r["id"],
                        crawl_scope=r.get("crawl_scope") or "configured",
                        rate_limit_delay=float(r.get("rate_limit_delay") or 1.0),
                        timeout=int(r.get("timeout") or 30),
                        enabled=bool(r.get("enabled", True)),
                        include_in_schedule=bool(r.get("include_in_schedule", True)),
                        status=r.get("status") or "READY",
                        last_error=r.get("last_error") or "",
                        last_attempt_at=r.get("last_attempt_at") or "",
                        last_success_at=r.get("last_success_at") or "",
                        created_at=r.get("created_at") or "",
                        updated_at=r.get("updated_at") or "",
                    )
                    session.add(item)
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _save_to_sqlite(item: dict[str, Any]) -> None:
        session = SessionLocal()
        try:
            db_item = session.query(CrawlerSourceItem).filter_by(id=item["id"]).first()
            if db_item is None:
                db_item = CrawlerSourceItem(
                    id=item["id"],
                    name=item.get("name") or item["id"],
                    description=item.get("description") or "",
                    seed_urls=item.get("seed_urls") or [],
                    adapter_mode=item.get("adapter_mode") or "specialized",
                    adapter_key=item.get("adapter_key") or item["id"],
                    crawl_scope=item.get("crawl_scope") or "configured",
                    rate_limit_delay=float(item.get("rate_limit_delay") or 1.0),
                    timeout=int(item.get("timeout") or 30),
                    enabled=bool(item.get("enabled", True)),
                    include_in_schedule=bool(item.get("include_in_schedule", True)),
                    status=item.get("status") or "READY",
                    last_error=item.get("last_error") or "",
                    last_attempt_at=item.get("last_attempt_at") or "",
                    last_success_at=item.get("last_success_at") or "",
                    created_at=item.get("created_at") or "",
                    updated_at=item.get("updated_at") or _now(),
                )
                session.add(db_item)
            else:
                db_item.name = item.get("name") or db_item.name
                db_item.description = item.get("description") or db_item.description
                db_item.seed_urls = item.get("seed_urls") or db_item.seed_urls
                db_item.adapter_mode = item.get("adapter_mode") or db_item.adapter_mode
                db_item.adapter_key = item.get("adapter_key") or db_item.adapter_key
                db_item.crawl_scope = item.get("crawl_scope") or db_item.crawl_scope
                db_item.rate_limit_delay = float(item.get("rate_limit_delay") or db_item.rate_limit_delay)
                db_item.timeout = int(item.get("timeout") or db_item.timeout)
                db_item.enabled = bool(item.get("enabled", db_item.enabled))
                db_item.include_in_schedule = bool(item.get("include_in_schedule", db_item.include_in_schedule))
                db_item.status = item.get("status") or db_item.status
                db_item.last_error = item.get("last_error") if item.get("last_error") is not None else db_item.last_error
                db_item.last_attempt_at = item.get("last_attempt_at") or db_item.last_attempt_at
                db_item.last_success_at = item.get("last_success_at") or db_item.last_success_at
                db_item.updated_at = item.get("updated_at") or _now()
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def bootstrap(self) -> dict[str, Any]:
        if self._sheets is not None and getattr(self._sheets, "configured", False):
            try:
                self.sheets.seed_source_rows(self._rows)
                existing_rows = self._clean_rows(self.sheets.get_source_rows())
                existing_by_id = {row["id"]: row for row in existing_rows}
                for seed in self._rows:
                    current = existing_by_id.get(seed["id"])
                    if current is None:
                        self.sheets.upsert_source_row(seed)
                        continue
                    if seed["id"] == "topcv" and current["seed_urls"] != seed["seed_urls"]:
                        migrated = {
                            **current,
                            "seed_urls": list(seed["seed_urls"]),
                            "adapter_mode": "specialized",
                            "adapter_key": "topcv",
                            "crawl_scope": "configured",
                            "updated_at": _now(),
                        }
                        self.sheets.upsert_source_row(migrated)
                return self.refresh()
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
                raise

        # SQLite storage (local primary database)
        try:
            self._seed_sqlite(self._rows)
            return self.refresh()
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            return self.snapshot()

    def refresh(self) -> dict[str, Any]:
        if self._sheets is not None and getattr(self._sheets, "configured", False):
            rows = self._clean_rows(self.sheets.get_source_rows())
            if not rows:
                raise RuntimeError("Worksheet Sources không có nguồn hợp lệ")
            source_name = "google_sheets"
        else:
            rows = self._clean_rows(self._load_from_sqlite())
            if not rows:
                rows = self._rows
            source_name = "sqlite"

        with self._lock:
            self._rows = rows
            self._source = source_name
            self._last_synced_at = _now()
            self._last_error = None
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = [dict(row) for row in self._rows]
            source = self._source
            last_synced_at = self._last_synced_at
            last_error = self._last_error
        return {
            "items": items,
            "total": len(items),
            "enabled_total": sum(1 for row in items if row["enabled"]),
            "source": source,
            "last_synced_at": last_synced_at,
            "last_error": last_error,
        }

    def get(self, source_id: str) -> dict[str, Any] | None:
        with self._lock:
            for row in self._rows:
                if row["id"] == source_id:
                    return dict(row)
        return None

    def enabled_sources(self, scheduled_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._rows
                if row["enabled"] and (not scheduled_only or row["include_in_schedule"])
            ]

    def _store(self, item: dict[str, Any]) -> None:
        with self._lock:
            for index, current in enumerate(self._rows):
                if current["id"] == item["id"]:
                    self._rows[index] = dict(item)
                    break
            else:
                self._rows.append(dict(item))

        if self._sheets is not None and getattr(self._sheets, "configured", False):
            try:
                self.sheets.upsert_source_row(item)
            except Exception:
                logger.exception("Không thể lưu trạng thái nguồn %s lên Google Sheets", item.get("id"))
                raise
            with self._lock:
                self._source = "google_sheets"
                self._last_synced_at = _now()
        else:
            self._save_to_sqlite(item)
            with self._lock:
                self._source = "sqlite"
                self._last_synced_at = _now()

    def add_url(self, name: str, url: str, include_in_schedule: bool = False) -> dict[str, Any]:
        """Persist exactly one user-named website source before probing it."""
        display_name = re.sub(r"\s+", " ", str(name or "")).strip()
        if not display_name:
            raise ValueError("Tên trang đang trống")
        if len(display_name) > 120:
            raise ValueError("Tên trang không được vượt quá 120 ký tự")
        raw_url = str(url or "").strip()
        if not raw_url:
            raise ValueError("URL đang trống")
        if "\n" in raw_url or "\r" in raw_url:
            raise ValueError("Mỗi lần chỉ được thêm một URL")
        normalized_url = normalize_source_url(raw_url)
        if not normalized_url:
            raise ValueError("URL không hợp lệ")

        existing_urls = {
            existing.casefold()
            for row in self.snapshot()["items"]
            for existing in row["seed_urls"]
        }
        if normalized_url.casefold() in existing_urls:
            return {
                "added": 0,
                "duplicates": 1,
                "needs_update": 0,
                "items": [],
                "total": self.snapshot()["total"],
            }

        parsed = urlparse(normalized_url)
        host = (parsed.hostname or "website").lower()
        suffix = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:8]
        slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-")[:32] or "website"
        valid, validation_error = validate_public_url(normalized_url)
        now = _now()
        item = {
            "id": f"custom-{slug}-{suffix}",
            "name": display_name,
            "description": "Nguồn website do người dùng thêm",
            "seed_urls": [normalized_url],
            "adapter_mode": "generic",
            "adapter_key": "generic",
            "crawl_scope": "full_site",
            "rate_limit_delay": 1.0,
            "timeout": min(int(settings.crawl_timeout_seconds), 30),
            "enabled": valid,
            "include_in_schedule": bool(include_in_schedule and valid),
            "status": "NEW" if valid else "NEEDS_ADAPTER",
            "last_error": "" if valid else ERROR_NOTICE,
            "last_attempt_at": now,
            "last_success_at": "",
            "created_at": now,
            "updated_at": now,
        }
        self._store(item)
        if not valid:
            logger.warning("Custom source validation failed for %s: %s", normalized_url, validation_error)
        return {
            "added": 1,
            "duplicates": 0,
            "needs_update": 0 if valid else 1,
            "items": [dict(item)],
            "total": self.snapshot()["total"],
        }

    async def probe(self, source_id: str) -> dict[str, Any]:
        item = self.get(source_id)
        if item is None:
            raise KeyError(source_id)
        url = item["seed_urls"][0]
        item["last_attempt_at"] = _now()
        try:
            valid, reason = await priority_coordinator.run_blocking(
                validate_public_url,
                url,
                worker_name="Source URL validation",
            )
            if not valid:
                raise RuntimeError(reason or "URL không an toàn")
            page = await browser_crawl_service.fetch(
                url,
                timeout=min(item["timeout"], 30),
                source_id=source_id,
            )
            final_valid, final_reason = await priority_coordinator.run_blocking(
                validate_public_url,
                page.url,
                worker_name="Source redirected URL validation",
            )
            if not final_valid:
                raise RuntimeError(final_reason or "Redirect không an toàn")
            content_type = (page.headers.get("Content-Type") or "").lower()
            if content_type and not any(value in content_type for value in ("html", "xml", "text")):
                raise RuntimeError("Nguồn không trả về HTML")
            if len(clean_html(page.html)) < 80:
                raise RuntimeError("Trang không có đủ nội dung sau khi render JavaScript")
            item.update(
                enabled=True,
                status="READY",
                last_error="",
                last_success_at=_now(),
                updated_at=_now(),
            )
        except Exception as exc:
            logger.warning("Custom source probe failed for %s: %s", url, exc)
            item.update(
                enabled=False,
                include_in_schedule=False,
                status="NEEDS_ADAPTER",
                last_error=ERROR_NOTICE,
                updated_at=_now(),
            )
        await priority_coordinator.run_blocking(
            self._store,
            item,
            worker_name="Save source probe status",
        )
        return item

    def record_status(self, source_id: str, status: str, error: Exception | str | None = None) -> None:
        item = self.get(source_id)
        if item is None:
            return
        now = _now()
        item["status"] = status
        item["last_attempt_at"] = now
        item["updated_at"] = now
        if error:
            logger.warning("Source %s requires update: %s", source_id, error)
            item["last_error"] = ERROR_NOTICE
            if item["adapter_mode"] == "generic":
                item["enabled"] = False
                item["include_in_schedule"] = False
                item["status"] = "NEEDS_ADAPTER"
        else:
            item["last_error"] = ""
            if status == "SUCCESS":
                item["last_success_at"] = now
        try:
            self._store(item)
        except Exception:
            logger.exception("Không thể lưu trạng thái nguồn %s lên Google Sheets", source_id)


source_service = SourceService()

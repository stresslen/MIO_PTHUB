from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any, Optional

from app.config import settings
from app.crawlers.base import ParsedItem, RawDocument, SourceAdapter
from app.pipeline.normalize import normalize_unicode, parse_datetime, utc_now
from app.services.keyword_service import keyword_service

logger = logging.getLogger(__name__)


class LinkedInApifyAdapter(SourceAdapter):
    """Search public LinkedIn posts with the configured Apify Actor."""

    def __init__(self):
        super().__init__(
            source_id="linkedin_apify",
            name="LinkedIn Posts (Apify)",
            seed_urls=["https://www.linkedin.com/search/results/content/"],
            rate_limit_delay=0,
            timeout=settings.apify_linkedin_run_timeout_seconds,
        )
        self._items_by_url: dict[str, dict[str, Any]] = {}
        self._last_run_id: str | None = None
        # Apify already searched using the enabled discovery keywords.
        # Valid results go straight to Gemini instead of the article pre-filter.
        self.is_keyword_feed = True

    @staticmethod
    def _value(item: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = item.get(key)
            if value not in (None, "", [], {}):
                return value
        return None

    @classmethod
    def _post_url(cls, item: dict[str, Any]) -> str:
        value = cls._value(
            item,
            "linkedinUrl",
            "linkedin_url",
            "postUrl",
            "post_url",
            "activityUrl",
            "activity_url",
            "url",
            "link",
        )
        return str(value or "").strip()

    @classmethod
    def _post_text(cls, item: dict[str, Any]) -> str:
        value = cls._value(
            item,
            "text",
            "content",
            "postText",
            "post_text",
            "commentary",
            "description",
            "summary",
        )
        if isinstance(value, dict):
            value = cls._value(value, "text", "content", "description")
        return normalize_unicode(str(value or ""))

    @classmethod
    def _author_details(cls, item: dict[str, Any]) -> tuple[str, str, str]:
        author = cls._value(item, "author", "postedBy", "posted_by", "actor")
        author_name = ""
        author_title = ""
        author_company = ""
        if isinstance(author, dict):
            author_name = str(
                cls._value(author, "name", "fullName", "full_name", "title") or ""
            ).strip()
            author_title = str(
                cls._value(author, "headline", "position", "jobTitle", "job_title") or ""
            ).strip()
            company = cls._value(author, "company", "companyName", "company_name")
            if isinstance(company, dict):
                company = cls._value(company, "name", "title")
            author_company = str(company or "").strip()
        else:
            author_name = str(author or "").strip()

        author_name = author_name or str(
            cls._value(item, "authorName", "author_name", "postedByName") or ""
        ).strip()
        author_title = author_title or str(
            cls._value(item, "authorHeadline", "author_title") or ""
        ).strip()
        author_company = author_company or str(
            cls._value(item, "authorCompany", "companyName", "company_name") or ""
        ).strip()
        return author_name, author_title, author_company

    @classmethod
    def _published_at(cls, item: dict[str, Any]) -> Optional[datetime.datetime]:
        value = cls._value(
            item,
            "postedAt",
            "posted_at",
            "publishedAt",
            "published_at",
            "postedDate",
            "posted_date",
            "date",
            "timestamp",
        )
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            try:
                return datetime.datetime.fromtimestamp(
                    timestamp, tz=datetime.timezone.utc
                ).replace(tzinfo=None)
            except (OverflowError, OSError, ValueError):
                return None
        return parse_datetime(str(value)) if value not in (None, "") else None

    def _actor_input(
        self,
        keywords: list[str],
        since: Optional[datetime.datetime],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "searchQueries": keywords,
            "maxPosts": settings.apify_linkedin_max_posts_per_keyword,
            "profileScraperMode": settings.apify_linkedin_profile_scraper_mode,
            "startPage": 1,
            "scrapeReactions": False,
            "reactionsProfileScraperMode": "short",
            "postNestedReactions": False,
            "scrapeComments": False,
            "commentsProfileScraperMode": "short",
            "postNestedComments": False,
            "contentType": settings.apify_linkedin_content_type,
            "sortBy": settings.apify_linkedin_sort_by,
        }
        if since is not None:
            payload["postedLimitDate"] = since.isoformat()
            age = utc_now() - since
            if age <= datetime.timedelta(days=1, minutes=5):
                payload["postedLimit"] = "24h"
            elif age <= datetime.timedelta(days=8):
                payload["postedLimit"] = "week"
            elif age <= datetime.timedelta(days=32):
                payload["postedLimit"] = "month"
            else:
                payload["postedLimit"] = "year"
        return payload

    def _run_actor(self, run_input: dict[str, Any]) -> list[dict[str, Any]]:
        if not settings.apify_api_token:
            raise RuntimeError(
                "APIFY_API_TOKEN chưa được cấu hình; LinkedIn không được crawl"
            )
        from apify_client import ApifyClient

        client = ApifyClient(settings.apify_api_token)
        run = client.actor(settings.apify_linkedin_actor_id).call(
            run_input=run_input,
            run_timeout=datetime.timedelta(
                seconds=settings.apify_linkedin_run_timeout_seconds
            ),
        )
        if run is None:
            raise RuntimeError("Apify Actor không trả về thông tin run")

        dataset_id = getattr(run, "default_dataset_id", None)
        run_id = getattr(run, "id", None)
        if dataset_id is None and isinstance(run, dict):
            dataset_id = run.get("defaultDatasetId")
            run_id = run.get("id")
        if not dataset_id:
            raise RuntimeError("Apify Actor không có default dataset")

        self._last_run_id = str(run_id or "")
        total_limit = settings.apify_linkedin_max_posts_per_keyword * max(
            1, len(run_input.get("searchQueries") or [])
        )
        return list(
            client.dataset(str(dataset_id)).iterate_items(limit=total_limit)
        )

    async def discover(
        self,
        since: Optional[datetime.datetime] = None,
        max_items: Optional[int] = None,
    ) -> list[str]:
        if not settings.apify_api_token:
            raise RuntimeError(
                "APIFY_API_TOKEN chưa được cấu hình; LinkedIn không được crawl"
            )
        config = keyword_service.get_config().get("discovery_search", {})
        keywords = [
            normalize_unicode(str(value))
            for value in config.get("keywords", [])
            if normalize_unicode(str(value))
        ]
        if not keywords:
            raise RuntimeError(
                "Không có keyword bật Search trực tiếp trong worksheet Keywords"
            )

        run_input = self._actor_input(keywords, since)
        logger.info(
            "[%s] Starting Apify actor for %s keywords, max %s posts/query",
            self.source_id,
            len(keywords),
            settings.apify_linkedin_max_posts_per_keyword,
        )
        items = await asyncio.to_thread(self._run_actor, run_input)

        self._items_by_url = {}
        urls: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = self._post_url(item)
            content = self._post_text(item)
            if not url.startswith(("https://www.linkedin.com/", "https://linkedin.com/")):
                continue
            if not content:
                continue
            if url in self._items_by_url:
                continue
            self._items_by_url[url] = item
            urls.append(url)
            if max_items and len(urls) >= max_items:
                break

        logger.info(
            "[%s] Apify run %s returned %s usable LinkedIn posts",
            self.source_id,
            self._last_run_id or "unknown",
            len(urls),
        )
        return urls

    async def fetch(self, url: str) -> RawDocument:
        item = self._items_by_url.get(url)
        if item is None:
            raise RuntimeError("Bài LinkedIn không tồn tại trong dataset Apify hiện tại")
        serialized = json.dumps(item, ensure_ascii=False, default=str)
        snapshot_path = self._save_snapshot(url, serialized)
        return RawDocument(
            url=url,
            source_id=self.source_id,
            fetched_at=utc_now(),
            html=serialized,
            text=self._post_text(item),
            headers={"Content-Type": "application/json", "X-Apify-Run-Id": self._last_run_id or ""},
            status_code=200,
            snapshot_path=str(snapshot_path),
        )

    async def parse(self, raw: RawDocument) -> ParsedItem:
        try:
            item = json.loads(raw.html)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Dataset Apify trả JSON không hợp lệ") from exc

        content = self._post_text(item)
        if not content:
            raise RuntimeError("Bài LinkedIn không có nội dung để Gemini xử lý")
        author_name, author_title, author_company = self._author_details(item)
        title_value = str(self._value(item, "title", "jobTitle", "job_title") or "").strip()
        title = title_value or content.splitlines()[0][:220]
        if not title:
            title = "Bài đăng LinkedIn"

        context_parts = [content]
        if author_name:
            context_parts.append(f"Tác giả công khai: {author_name}")
        if author_title:
            context_parts.append(f"Chức danh công khai: {author_title}")
        if author_company:
            context_parts.append(f"Đơn vị công khai: {author_company}")

        return ParsedItem(
            url=raw.url,
            source_id=self.source_id,
            title=title,
            raw_content="\n".join(context_parts),
            published_at=self._published_at(item),
            author=author_name or None,
            extra_metadata={
                "author_title": author_title,
                "author_company": author_company,
                "apify_run_id": self._last_run_id,
            },
        )

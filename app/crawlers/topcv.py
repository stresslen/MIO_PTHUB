from __future__ import annotations

import datetime
import json
import logging
import re
import unicodedata
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.config import settings
from app.crawlers.base import ParsedItem, RawDocument, SourceAdapter, extract_published_at
from app.pipeline.normalize import canonicalize_url, clean_html, normalize_unicode, parse_datetime, utc_now
from app.services.priority_service import priority_coordinator

logger = logging.getLogger(__name__)
TOPCV_ROOT_URL = "https://www.topcv.vn/"
JOB_URL_RE = re.compile(r"^https://(?:www\.)?topcv\.vn/viec-lam/[^?#]+/\d+\.html$", re.I)
CHALLENGE_MARKERS = ("cf-chl-", "just a moment", "verify you are human", "checking your browser")


class TopCVAdapter(SourceAdapter):
    """Crawl TopCV with Crawl4AI's Playwright browser, without HTTP fallback."""

    is_keyword_feed = True

    def __init__(self):
        super().__init__("topcv", "TopCV · Việc làm chuyển đổi số", [TOPCV_ROOT_URL], 0.5, 90)
        self._document_cache: dict[str, RawDocument] = {}

    @staticmethod
    def _crawl4ai_types():
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig, UndetectedAdapter
            from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
        except ImportError as exc:
            raise RuntimeError("Thiếu Crawl4AI/Patchright và Chromium để crawl TopCV") from exc
        return AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig, UndetectedAdapter, AsyncPlaywrightCrawlerStrategy

    @staticmethod
    def _slugify_keyword(value: str) -> str:
        value = value.replace("Đ", "D").replace("đ", "d")
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    def _search_urls(self) -> list[str]:
        urls: list[str] = []
        # TopCV search formula: /tim-viec-lam-{hyphenated-keyword}
        for keyword in self._discovery_search_keywords():
            slug = self._slugify_keyword(keyword)
            if slug:
                urls.append(f"https://www.topcv.vn/tim-viec-lam-{slug}?type_keyword=1&sba=1")
        if not urls:
            raise RuntimeError("Không có keyword bật Search trực tiếp trong worksheet Keywords")
        return urls

    @staticmethod
    def _with_page(url: str, page: int) -> str:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if page > 1:
            query["page"] = str(page)
        else:
            query.pop("page", None)
        return urlunparse(parsed._replace(query=urlencode(query)))

    @staticmethod
    def _extract_job_urls(html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html or "", "html.parser")
        urls: list[str] = []
        for anchor in soup.find_all("a", href=True):
            candidate = canonicalize_url(urljoin(base_url, str(anchor.get("href") or "")))
            parsed = urlparse(candidate)
            candidate = urlunparse(parsed._replace(query="", fragment=""))
            if JOB_URL_RE.match(candidate) and candidate not in urls:
                urls.append(candidate)
        return urls

    def _browser_config(self, BrowserConfig):
        return BrowserConfig(
            browser_type="chromium",
            headless=True,
            enable_stealth=True,
            user_agent_mode="random",
            user_agent_generator_config={"platforms": "desktop", "os": "Linux"},
            memory_saving_mode=True,
            avoid_ads=True,
            verbose=False,
            extra_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )

    def _run_config(self, CrawlerRunConfig, CacheMode, *, listing: bool):
        return CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="load",
            page_timeout=self.timeout * 1000,
            wait_for="css:body",
            delay_before_return_html=2.0,
            proxy_config=settings.topcv_proxy_url or None,
            max_retries=1 if settings.topcv_proxy_url else 0,
            wait_for_timeout=min(self.timeout * 1000, 30_000),
            scan_full_page=listing,
            scroll_delay=0.3,
            simulate_user=True,
            override_navigator=True,
            magic=True,
            remove_overlay_elements=True,
            remove_consent_popups=True,
        )

    def _raw_from_result(self, result: Any, requested_url: str) -> RawDocument:
        status = int(getattr(result, "status_code", 0) or 0)
        html = str(getattr(result, "html", "") or "")
        error = str(getattr(result, "error_message", "") or "").strip()
        final_url = canonicalize_url(
            str(getattr(result, "redirected_url", "") or getattr(result, "url", "") or requested_url)
        )
        if not bool(getattr(result, "success", False)) or status >= 400:
            raise RuntimeError(f"TopCV browser trả lỗi HTTP {status or 'unknown'}: {error or requested_url}")
        if not html.strip() or any(marker in html[:30_000].lower() for marker in CHALLENGE_MARKERS):
            raise RuntimeError("TopCV đang chặn trình duyệt tự động bằng trang xác minh")
        snapshot = self._save_snapshot(final_url, html)
        return RawDocument(
            url=final_url,
            source_id=self.source_id,
            fetched_at=utc_now(),
            html=html,
            text=clean_html(html),
            headers=dict(getattr(result, "response_headers", {}) or {}),
            status_code=status or 200,
            snapshot_path=str(snapshot),
        )

    async def _crawl_page(self, crawler: Any, url: str, config: Any) -> RawDocument:
        if not priority_coordinator.is_current_task_frontend:
            await priority_coordinator.yield_if_fe_active(f"TopCV {url}")
        result = await crawler.arun(url=url, config=config)
        return self._raw_from_result(result, url)

    def _new_crawler(self, AsyncWebCrawler, BrowserConfig, UndetectedAdapter, Strategy):
        browser_config = self._browser_config(BrowserConfig)
        crawler_strategy = Strategy(
            browser_config=browser_config,
            browser_adapter=UndetectedAdapter(),
        )
        return AsyncWebCrawler(
            crawler_strategy=crawler_strategy,
            config=browser_config,
        )

    async def _fetch_one_with_browser(self, url: str) -> RawDocument:
        AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig, UndetectedAdapter, Strategy = self._crawl4ai_types()
        async with self._new_crawler(AsyncWebCrawler, BrowserConfig, UndetectedAdapter, Strategy) as crawler:
            return await self._crawl_page(
                crawler, url, self._run_config(CrawlerRunConfig, CacheMode, listing=False)
            )

    async def discover(
        self,
        since: Optional[datetime.datetime] = None,
        max_items: Optional[int] = None,
    ) -> list[str]:
        # This source is limited by timeframe and finite pagination, not an item cap.
        del max_items
        AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig, UndetectedAdapter, Strategy = self._crawl4ai_types()
        listing_config = self._run_config(CrawlerRunConfig, CacheMode, listing=True)
        detail_config = self._run_config(CrawlerRunConfig, CacheMode, listing=False)
        discovered: list[str] = []
        seen_urls: set[str] = set()
        async with self._new_crawler(AsyncWebCrawler, BrowserConfig, UndetectedAdapter, Strategy) as crawler:
            for search_url in self._search_urls():
                page = 1
                while True:
                    listing = await self._crawl_page(
                        crawler, self._with_page(search_url, page), listing_config
                    )
                    fresh_urls = [
                        url for url in self._extract_job_urls(listing.html, listing.url)
                        if url not in seen_urls
                    ]
                    if not fresh_urls:
                        break
                    seen_urls.update(fresh_urls)
                    for job_url in fresh_urls:
                        try:
                            raw = await self._crawl_page(crawler, job_url, detail_config)
                            parsed = await self.parse(raw)
                            if since and parsed.published_at and parsed.published_at < since:
                                continue
                            self._document_cache[job_url] = raw
                            discovered.append(job_url)
                        except Exception as exc:
                            logger.warning("[%s] Không crawl được %s: %s", self.source_id, job_url, exc)
                    page += 1
        logger.info("[%s] Tìm thấy %s tin tuyển dụng trong khoảng thời gian", self.source_id, len(discovered))
        return discovered

    async def fetch(self, url: str) -> RawDocument:
        url = canonicalize_url(url)
        if url in self._document_cache:
            return self._document_cache[url]
        if not JOB_URL_RE.match(url):
            raise RuntimeError("URL TopCV không phải trang chi tiết việc làm hợp lệ")
        raw = await self._fetch_one_with_browser(url)
        self._document_cache[url] = raw
        return raw

    @staticmethod
    def _json_ld_values(soup: BeautifulSoup) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for node in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
            try:
                payload = json.loads(node.string or node.get_text() or "")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            queue = payload if isinstance(payload, list) else [payload]
            values.extend(item for item in queue if isinstance(item, dict))
        return values

    async def parse(self, raw: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw.html, "html.parser")
        schema = next(
            (item for item in self._json_ld_values(soup) if str(item.get("@type", "")).lower() == "jobposting"),
            {},
        )
        title_node = soup.find("h1")
        title = normalize_unicode(str(schema.get("title") or "")) or normalize_unicode(
            title_node.get_text(" ", strip=True) if title_node else ""
        )
        company_data = schema.get("hiringOrganization") or {}
        company = normalize_unicode(
            str(company_data.get("name") or "") if isinstance(company_data, dict) else ""
        )
        if not company:
            company_node = soup.select_one("[class*='company-name'], [class*='company_name'], .company-name-label")
            company = normalize_unicode(company_node.get_text(" ", strip=True) if company_node else "")
        published_at = (
            parse_datetime(str(schema.get("datePosted") or ""))
            or extract_published_at(soup, raw.text, title)
        )
        for node in soup([
            "script", "style", "noscript", "template", "svg", "canvas",
            "form", "nav", "header", "footer", "aside",
        ]):
            node.decompose()
        content_node = (
            soup.select_one("[class*='job-detail__information-detail']")
            or soup.select_one("[class*='job-description']")
            or soup.find("main")
            or soup.body
            or soup
        )
        content = normalize_unicode(content_node.get_text(" ", strip=True))
        if len(content) < 80:
            raise RuntimeError("Trang TopCV không có đủ nội dung việc làm sau khi render")
        if not title:
            raise RuntimeError("Không trích xuất được tiêu đề việc làm TopCV")
        if company:
            content = f"Đơn vị tuyển dụng: {company}\n{content}"
        return ParsedItem(
            url=raw.url,
            source_id=self.source_id,
            title=title[:500],
            raw_content=content,
            published_at=published_at,
            author=company or None,
            extra_metadata={
                "adapter": "topcv_crawl4ai_playwright",
                "signal_type": "Hiring",
                "company": company,
            },
        )

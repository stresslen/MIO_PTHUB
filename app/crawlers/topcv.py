from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.config import settings
from app.crawlers.base import ParsedItem, RawDocument, SourceAdapter, extract_published_at
from app.pipeline.normalize import canonicalize_url, clean_html, normalize_unicode, parse_datetime, utc_now
from app.services.priority_service import BackgroundPreemptedError, priority_coordinator

logger = logging.getLogger(__name__)
TOPCV_ROOT_URL = "https://www.topcv.vn/"
JOB_URL_RE = re.compile(r"^https://(?:www\.)?topcv\.vn/viec-lam/[^?#]+/\d+\.html", re.I)
CHALLENGE_MARKERS = (
    "cf-chl-",
    "challenges.cloudflare.com",
    "just a moment",
    "verify you are human",
    "checking your browser",
)
PROFILE_ROOT = Path(__file__).resolve().parents[2] / "profiles"


class TopCVAdapter(SourceAdapter):
    """Crawl TopCV with Crawl4AI's Playwright browser, without HTTP fallback."""

    is_keyword_feed = True

    def __init__(self):
        super().__init__("topcv", "TopCV · Việc làm chuyển đổi số", [TOPCV_ROOT_URL], 10.0, 90)
        self._document_cache: dict[str, RawDocument] = {}
        self._parsed_cache: dict[str, ParsedItem] = {}

    @staticmethod
    def _crawl4ai_types():
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        except ImportError as exc:
            raise RuntimeError("Thiếu Crawl4AI/Patchright và Chromium để crawl TopCV") from exc
        return AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    @staticmethod
    def _slugify_keyword(value: str) -> str:
        value = value.replace("Đ", "D").replace("đ", "d")
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    def _search_urls(self, max_queries: int = 3) -> list[str]:
        urls: list[str] = []
        # TopCV search formula: /tim-viec-lam-{hyphenated-keyword}
        for keyword in self._discovery_search_keywords(max_items=max_queries):
            slug = self._slugify_keyword(keyword)
            if slug:
                urls.append(f"https://www.topcv.vn/tim-viec-lam-{slug}?type_keyword=1&sba=1")
        if not urls:
            urls.append("https://www.topcv.vn/tim-viec-lam-chuyen-doi-so?type_keyword=1&sba=1")
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

    def _extract_job_cards(self, html: str, base_url: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html or "", "html.parser")
        cards = soup.select(".job-item-2, .job-item-search-result, .job-item, [class*='job-item']")
        extracted: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for card in cards:
            job_url = None
            for a in card.find_all("a", href=True):
                candidate = canonicalize_url(urljoin(base_url, str(a.get("href") or "")))
                candidate = urlunparse(urlparse(candidate)._replace(query="", fragment=""))
                if JOB_URL_RE.match(candidate):
                    job_url = candidate
                    break
            if not job_url or job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            # Title
            title = ""
            title_node = card.select_one("h3 a, .title a, a[class*='title'], h3, h2")
            if title_node:
                title = normalize_unicode(title_node.get_text(strip=True))
            if not title:
                for a in card.find_all("a", href=True):
                    candidate = canonicalize_url(urljoin(base_url, str(a.get("href") or "")))
                    if JOB_URL_RE.match(candidate):
                        t = normalize_unicode(a.get_text(strip=True))
                        if t and len(t) > 3:
                            title = t
                            break

            # Company
            company_node = card.select_one(".company, .company-name, [class*='company']")
            company = normalize_unicode(company_node.get_text(strip=True) if company_node else "")
            company = re.sub(r"^(?:Pro|Vip)\s*", "", company, flags=re.I).strip()

            # Date calculation from card badge text
            card_text = normalize_unicode(card.get_text(" | ", strip=True))
            now = utc_now()
            published_at = now
            if "hôm nay" in card_text.lower():
                published_at = now
            elif "hôm qua" in card_text.lower():
                published_at = now - datetime.timedelta(days=1)
            else:
                day_match = re.search(r"(\d+)\s*ngày\s*trước", card_text, re.I)
                week_match = re.search(r"(\d+)\s*tuần\s*trước", card_text, re.I)
                month_match = re.search(r"(\d+)\s*tháng\s*trước", card_text, re.I)
                if day_match:
                    published_at = now - datetime.timedelta(days=int(day_match.group(1)))
                elif week_match:
                    published_at = now - datetime.timedelta(weeks=int(week_match.group(1)))
                elif month_match:
                    published_at = now - datetime.timedelta(days=int(month_match.group(1)) * 30)

            extracted.append({
                "url": job_url,
                "title": title or "Cơ hội việc làm",
                "company": company,
                "published_at": published_at,
                "card_html": str(card),
                "card_text": card_text,
            })

        return extracted

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

    @staticmethod
    def _profile_dir(url: str) -> str:
        """Return one stable persistent Chromium profile for each TopCV URL."""
        url_key = hashlib.sha256(canonicalize_url(url).encode("utf-8")).hexdigest()[:16]
        return str(PROFILE_ROOT / f"topcv-zero-delay-{url_key}")

    def _browser_config(self, BrowserConfig, url: str):
        return BrowserConfig(
            browser_type="chromium",
            headless=True,
            java_script_enabled=True,
            use_persistent_context=True,
            user_data_dir=self._profile_dir(url),
            verbose=False,
        )

    def _run_config(self, CrawlerRunConfig, CacheMode, *, listing: bool):
        return CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="commit",
            page_timeout=30_000,
            delay_before_return_html=3.0,
            proxy_config=settings.topcv_proxy_url or None,
            max_retries=1 if settings.topcv_proxy_url else 0,
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
        while True:
            try:
                result = await priority_coordinator.run_async(
                    crawler.arun,
                    url=url,
                    config=config,
                    worker_name=f"TopCV {url}",
                )
                return self._raw_from_result(result, url)
            except BackgroundPreemptedError:
                # Retry the same listing/detail only after FE releases priority.
                await priority_coordinator.yield_if_fe_active(f"TopCV {url}")

    def _new_crawler(self, AsyncWebCrawler, BrowserConfig, url: str):
        return AsyncWebCrawler(config=self._browser_config(BrowserConfig, url))

    async def _crawl_url_with_browser(self, url: str, config: Any) -> RawDocument:
        AsyncWebCrawler, BrowserConfig, _, _ = self._crawl4ai_types()
        logger.info("[%s] Mở browser/profile riêng cho URL: %s", self.source_id, url)
        async with self._new_crawler(AsyncWebCrawler, BrowserConfig, url) as crawler:
            return await self._crawl_page(crawler, url, config)

    async def _fetch_one_with_browser(self, url: str) -> RawDocument:
        _, _, CacheMode, CrawlerRunConfig = self._crawl4ai_types()
        return await self._crawl_url_with_browser(
            url,
            self._run_config(CrawlerRunConfig, CacheMode, listing=False),
        )

    async def discover(
        self,
        since: Optional[datetime.datetime] = None,
        max_items: Optional[int] = None,
    ) -> list[str]:
        """Search and crawl TopCV sequentially, one keyword at a time.

        Each listing/detail URL gets its own browser and persistent Chromium
        profile. Browsers are started sequentially without an artificial delay.
        """
        _, _, CacheMode, CrawlerRunConfig = self._crawl4ai_types()
        listing_config = self._run_config(CrawlerRunConfig, CacheMode, listing=True)
        detail_config = self._run_config(CrawlerRunConfig, CacheMode, listing=False)
        discovered: list[str] = []
        seen_urls: set[str] = set()
        # A singleton adapter may be reused by multiple crawl runs; never reuse
        # documents or parsed metadata from a previous run.
        self._document_cache.clear()
        self._parsed_cache.clear()

        since_naive = since.replace(tzinfo=None) if since and getattr(since, "tzinfo", None) else since

        search_urls = self._search_urls(max_queries=3)
        for search_url in search_urls:
            if max_items and len(discovered) >= max_items:
                break
            logger.info("[%s] Search keyword/listing: %s", self.source_id, search_url)
            try:
                listing = await self._crawl_url_with_browser(search_url, listing_config)
            except Exception as exc:
                logger.warning(
                    "[%s] Không tải được trang tìm kiếm %s: %s",
                    self.source_id,
                    search_url,
                    exc,
                )
                continue

            job_cards = self._extract_job_cards(listing.html, listing.url)
            logger.info(
                "[%s] Keyword listing trả về %s job card; bắt đầu crawl detail ngay",
                self.source_id,
                len(job_cards),
            )

            for card in job_cards:
                if max_items and len(discovered) >= max_items:
                    break
                job_url = card["url"]
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                published_at = card["published_at"]
                pub_naive = (
                    published_at.replace(tzinfo=None)
                    if published_at and getattr(published_at, "tzinfo", None)
                    else published_at
                )
                if since_naive and pub_naive and pub_naive < since_naive:
                    continue

                try:
                    # Critical anti-bot behavior: crawl this detail URL before
                    # moving to the next card or the next keyword listing.
                    raw_doc = await self._crawl_url_with_browser(job_url, detail_config)
                    self._document_cache[job_url] = raw_doc
                    parsed = await self.parse(raw_doc)
                    if not parsed.published_at:
                        parsed.published_at = published_at
                    parsed_published_naive = (
                        parsed.published_at.replace(tzinfo=None)
                        if parsed.published_at and getattr(parsed.published_at, "tzinfo", None)
                        else parsed.published_at
                    )
                    if since_naive and parsed_published_naive and parsed_published_naive < since_naive:
                        logger.info(
                            "[%s] Bỏ qua detail cũ %s (published %s ngoài %s)",
                            self.source_id,
                            job_url,
                            parsed.published_at,
                            since,
                        )
                        continue
                    self._parsed_cache[job_url] = parsed
                    discovered.append(job_url)
                    logger.info(
                        "[%s] Search-crawl hoàn tất detail %s (%s/%s)",
                        self.source_id,
                        job_url,
                        len(discovered),
                        len(job_cards),
                    )
                except Exception as exc:
                    logger.warning(
                        "[%s] Bỏ qua job detail sau keyword listing %s: %s",
                        self.source_id,
                        job_url,
                        exc,
                    )
        logger.info(
            "[%s] Hoàn tất search-crawl theo từng keyword; %s job detail sẵn sàng cho pipeline",
            self.source_id,
            len(discovered),
        )
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
        if raw.url in self._parsed_cache:
            return self._parsed_cache[raw.url]

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
        # Keep the complete rendered job page, including public header/footer/contact data.
        content = clean_html(raw.html)
        if not content.strip():
            raise RuntimeError("Trang TopCV không có nội dung việc làm sau khi render")
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

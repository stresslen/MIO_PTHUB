from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.pipeline.normalize import canonicalize_url
from app.services.priority_service import BackgroundPreemptedError, priority_coordinator

logger = logging.getLogger(__name__)

_CHALLENGE_MARKERS = (
    "cf-chl-",
    "just a moment",
    "verify you are human",
    "checking your browser",
)


@dataclass(slots=True)
class BrowserPage:
    url: str
    html: str
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)


class BrowserCrawlService:
    """One shared Crawl4AI browser for every HTML/JavaScript source.

    The browser starts only on the first crawl. Crawl4AI opens an isolated page for
    each ``arun`` call, so a foreground request does not have to wait for the
    currently running background page. Background work still cooperates with the
    existing frontend-priority coordinator before it starts another navigation.
    """

    def __init__(self) -> None:
        self._crawler: Any | None = None
        self._start_lock = asyncio.Lock()

    @staticmethod
    def _types():
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        except ImportError as exc:
            raise RuntimeError(
                "Thiếu Crawl4AI hoặc Chromium. Hãy cài requirements và chạy "
                "`python -m playwright install chromium`."
            ) from exc
        return AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    async def _get_crawler(self) -> Any:
        if self._crawler is not None:
            return self._crawler
        async with self._start_lock:
            if self._crawler is not None:
                return self._crawler
            AsyncWebCrawler, BrowserConfig, _, _ = self._types()
            browser_config = BrowserConfig(
                browser_type="chromium",
                headless=True,
                enable_stealth=True,
                java_script_enabled=True,
                ignore_https_errors=True,
                memory_saving_mode=True,
                avoid_ads=True,
                verbose=False,
                user_agent=settings.crawler_user_agent,
                headers={
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                },
                extra_args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            crawler = AsyncWebCrawler(
                config=browser_config,
                base_directory="/tmp/mio-crawl4ai",
            )
            try:
                await crawler.start()
            except Exception:
                try:
                    await crawler.close()
                except Exception:
                    logger.debug("Crawl4AI cleanup after startup failure failed", exc_info=True)
                raise
            self._crawler = crawler
            logger.info("Shared Crawl4AI browser started")
            return crawler

    async def fetch(self, url: str, *, timeout: int, source_id: str) -> BrowserPage:
        if not priority_coordinator.is_current_task_frontend:
            await priority_coordinator.yield_if_fe_active(f"Crawl4AI {source_id}")

        _, _, CacheMode, CrawlerRunConfig = self._types()
        crawler = await self._get_crawler()
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="domcontentloaded",
            page_timeout=max(1, timeout) * 1000,
            delay_before_return_html=0.75,
            ignore_body_visibility=True,
            process_iframes=False,
            flatten_shadow_dom=True,
            simulate_user=True,
            override_navigator=True,
            magic=True,
            remove_overlay_elements=True,
            remove_consent_popups=True,
            max_retries=0,
        )
        while True:
            try:
                result = await priority_coordinator.run_async(
                    crawler.arun,
                    url=url,
                    config=run_config,
                    worker_name=f"Crawl4AI {source_id}",
                )
                break
            except BackgroundPreemptedError:
                # Resume this exact URL after FE releases priority. This avoids
                # losing a seed/detail page while preventing hot retries.
                await priority_coordinator.yield_if_fe_active(f"Crawl4AI {source_id}")
        status = int(getattr(result, "status_code", 0) or 0)
        html = str(getattr(result, "html", "") or "")
        error = str(getattr(result, "error_message", "") or "").strip()
        final_url = canonicalize_url(
            str(
                getattr(result, "redirected_url", "")
                or getattr(result, "url", "")
                or url
            )
        )
        if not bool(getattr(result, "success", False)) or status >= 400:
            raise RuntimeError(
                f"Crawl4AI trả lỗi HTTP {status or 'unknown'}: {error or final_url}"
            )
        if not html.strip():
            raise RuntimeError("Crawl4AI không nhận được HTML sau khi render")
        lowered = html[:30_000].lower()
        if any(marker in lowered for marker in _CHALLENGE_MARKERS):
            raise RuntimeError("Website đang chặn trình duyệt tự động bằng trang xác minh")

        headers = {
            str(key).title(): str(value)
            for key, value in dict(getattr(result, "response_headers", {}) or {}).items()
        }
        return BrowserPage(
            url=final_url,
            html=html,
            status_code=status or 200,
            headers=headers,
        )

    async def close(self) -> None:
        async with self._start_lock:
            crawler, self._crawler = self._crawler, None
            if crawler is not None:
                await crawler.close()
                logger.info("Shared Crawl4AI browser stopped")


browser_crawl_service = BrowserCrawlService()

from __future__ import annotations

import datetime
import logging
import re
from collections import deque
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.crawlers.base import (
    ParsedItem,
    RawDocument,
    SourceAdapter,
    extract_published_at,
)
from app.pipeline.normalize import canonicalize_url, clean_html, normalize_unicode
from app.services.source_service import (
    CUSTOM_MAX_DEPTH,
    CUSTOM_MAX_PAGES,
    validate_public_url,
)

logger = logging.getLogger(__name__)

SKIP_EXTENSIONS = re.compile(
    r"\.(?:7z|avi|bin|bmp|css|csv|docx?|eot|exe|gif|gz|ico|jpe?g|js|json|"
    r"m4a|mkv|mov|mp3|mp4|mpeg|pdf|png|pptx?|rar|rss|svg|tar|tiff?|ttf|"
    r"webm|webp|woff2?|xlsx?|xml|zip)(?:$|[?#])",
    re.IGNORECASE,
)
SKIP_PATH_PARTS = re.compile(
    r"/(?:login|logout|signin|signup|register|cart|checkout|wp-admin)(?:/|$)",
    re.IGNORECASE,
)


class GenericWebsiteAdapter(SourceAdapter):
    """Deterministic same-domain crawler for user-managed website URLs."""

    is_generic = True

    def __init__(self, source: dict):
        super().__init__(
            source_id=source["id"],
            name=source["name"],
            seed_urls=list(source["seed_urls"]),
            rate_limit_delay=float(source.get("rate_limit_delay") or 1.0),
            timeout=int(source.get("timeout") or 30),
        )
        self.max_pages = CUSTOM_MAX_PAGES
        self.max_depth = CUSTOM_MAX_DEPTH
        self._document_cache: dict[str, RawDocument] = {}
        self._root_hosts = {
            self._host_key(urlparse(url).hostname or "")
            for url in self.seed_urls
        }

    @staticmethod
    def _host_key(host: str) -> str:
        value = host.lower().strip(".")
        return value.removeprefix("www.")

    def _allowed_url(self, url: str) -> bool:
        valid, _ = validate_public_url(url, resolve_dns=False)
        if not valid:
            return False
        parsed = urlparse(url)
        if self._host_key(parsed.hostname or "") not in self._root_hosts:
            return False
        if not parsed.path.lower().endswith("/sitemap.xml") and SKIP_EXTENSIONS.search(url):
            return False
        if SKIP_PATH_PARTS.search(parsed.path):
            return False
        return parsed.scheme in {"http", "https"}

    async def fetch(self, url: str) -> RawDocument:
        clean_url = canonicalize_url(url)
        if not self._allowed_url(clean_url):
            raise RuntimeError("URL nằm ngoài domain hoặc không an toàn")
        cached = self._document_cache.get(clean_url)
        if cached is not None:
            return cached
        document = await super().fetch(clean_url)
        if not self._allowed_url(document.url):
            raise RuntimeError("Redirect ra ngoài domain hoặc tới địa chỉ không an toàn")
        self._document_cache[clean_url] = document
        return document

    async def _sitemap_urls(self, limit: int) -> list[str]:
        roots: list[str] = []
        for seed in self.seed_urls:
            parsed = urlparse(seed)
            sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
            try:
                document = await self.fetch(sitemap_url)
                soup = BeautifulSoup(document.html, "xml")
                for node in soup.find_all("loc"):
                    value = canonicalize_url(node.get_text(strip=True))
                    if value and self._allowed_url(value) and value not in roots:
                        roots.append(value)
                        if len(roots) >= limit:
                            return roots
            except Exception as exc:
                logger.info("[%s] Sitemap unavailable: %s", self.source_id, exc)
        return roots

    async def discover(
        self,
        since: Optional[datetime.datetime] = None,
        max_items: Optional[int] = None,
    ) -> List[str]:
        limit = min(max_items or self.max_pages, self.max_pages)
        sitemap_urls = await self._sitemap_urls(limit)
        queue = deque(
            [(canonicalize_url(url), 0) for url in self.seed_urls]
            + [(url, 1) for url in sitemap_urls]
        )
        queued = {url for url, _ in queue}
        discovered: list[str] = []
        failures: list[str] = []

        while queue and len(discovered) < limit:
            url, depth = queue.popleft()
            try:
                document = await self.fetch(url)
                content_type = (document.headers.get("Content-Type") or "").lower()
                if content_type and not any(value in content_type for value in ("html", "xml", "text")):
                    continue
                if url.endswith("/sitemap.xml"):
                    continue
                discovered.append(url)
                if depth >= self.max_depth:
                    continue
                soup = BeautifulSoup(document.html, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    href = str(anchor.get("href") or "").strip()
                    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                        continue
                    candidate = canonicalize_url(urljoin(url, href))
                    if not candidate or candidate in queued or not self._allowed_url(candidate):
                        continue
                    queued.add(candidate)
                    queue.append((candidate, depth + 1))
                    if len(queued) >= limit * 6:
                        break
            except Exception as exc:
                failures.append(f"{url}: {exc}")
                logger.warning("[%s] Generic discovery failed for %s: %s", self.source_id, url, exc)

        if not discovered:
            detail = failures[0] if failures else "không tìm thấy trang HTML"
            raise RuntimeError(f"Không crawl được website: {detail}")
        return discovered

    async def parse(self, raw: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw.html, "html.parser")
        title_node = soup.find("h1") or soup.find("title")
        title = normalize_unicode(title_node.get_text(" ", strip=True) if title_node else "")
        if not title:
            title = urlparse(raw.url).path.strip("/").replace("-", " ") or self.name

        published_at = extract_published_at(soup, raw.text, title)
        # Parse the complete document body instead of selecting article/main only.
        # clean_html keeps header/footer/nav/aside/form and converts mailto/tel into text.
        content_node = soup.body or soup
        body_text = clean_html(str(content_node))
        if not body_text.strip():
            raise RuntimeError("Trang không có nội dung text")

        return ParsedItem(
            url=raw.url,
            source_id=self.source_id,
            title=title[:500],
            raw_content=body_text,
            published_at=published_at,
            author=None,
            extra_metadata={"adapter": "generic", "cleaned_html": True, "kept_layout_sections": True},
        )

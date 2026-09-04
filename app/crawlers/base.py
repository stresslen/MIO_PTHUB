from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import math
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.config import RAW_DATA_DIR, settings
from app.services.browser_crawl_service import browser_crawl_service
from app.services.priority_service import BackgroundPreemptedError
from app.services.keyword_service import keyword_service
from app.pipeline.normalize import canonicalize_url, clean_html, normalize_unicode, parse_datetime, utc_now

logger = logging.getLogger(__name__)


_DATE_VALUE_RE = re.compile(
    r"(?:\d{1,2}:\d{2}(?::\d{2})?\s+\d{1,2}[/.-]\d{1,2}[/.-]\d{4}"
    r"|\d{4}-\d{1,2}-\d{1,2}(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?"
    r"|\d{1,2}[/.-]\d{1,2}[/.-]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
    re.IGNORECASE,
)
_NON_PUBLISHED_CONTEXT_RE = re.compile(
    r"hạn|đóng thầu|mở thầu|hạn chót|deadline|trước ngày|đến ngày|ngày phê duyệt|thời gian thực hiện",
    re.IGNORECASE,
)


def _published_candidate(value: Any) -> Optional[datetime.datetime]:
    """Parse a date only when its local context does not describe a deadline/event date."""
    if value is None:
        return None
    candidate = normalize_unicode(str(value))
    if not candidate or _NON_PUBLISHED_CONTEXT_RE.search(candidate):
        return None
    match = _DATE_VALUE_RE.search(candidate)
    return parse_datetime(match.group(0)) if match else parse_datetime(candidate)


def _json_date_published(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() == "datepublished":
                parsed = _published_candidate(item)
                if parsed:
                    return parsed
        for item in value.values():
            parsed = _json_date_published(item)
            if parsed:
                return parsed
    elif isinstance(value, list):
        for item in value:
            parsed = _json_date_published(item)
            if parsed:
                return parsed
    return None


def extract_published_at(soup: Any, raw_text: str = "", title: str = "") -> Optional[datetime.datetime]:
    """Extract article publication time using trustworthy, ordered evidence.

    Priority: schema.org datePublished, explicit publication meta, semantic time/date
    elements, then publication-labelled text. A bare date from the title/body is never
    accepted because it is commonly a deadline, event date, or approval date.
    """
    # 1. schema.org JSON-LD datePublished
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            payload = json.loads(script.string or script.get_text() or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        parsed = _json_date_published(payload)
        if parsed:
            return parsed

    # 2. Explicit publication metadata. Never use dateModified/updated fields.
    for meta in soup.find_all("meta"):
        marker = " ".join(str(meta.get(key, "")) for key in ("property", "name", "itemprop", "id")).lower()
        if any(word in marker for word in ("modified", "updated", "lastmod")):
            continue
        if any(word in marker for word in ("datepublished", "published_time", "publishdate", "pubdate", "publication_date", "article:published")):
            parsed = _published_candidate(meta.get("content") or meta.get("datetime"))
            if parsed:
                return parsed

    # 3. Explicit publication-labelled text outranks generic date elements. only dates carrying an explicit publication label.
    labelled = re.search(
        r"(?:ngày\s*đăng(?:\s*tải)?|thời\s*điểm\s*đăng(?:\s*tải)?|đăng\s*lúc|ngày\s*xuất\s*bản|xuất\s*bản|published(?:\s+at)?|phát\s*hành)"
        r"\s*[:\-]?\s*((?:\d{1,2}:\d{2}\s+)?\d{1,2}[/.-]\d{1,2}[/.-]\d{4}(?:\s+\d{1,2}:\d{2})?)",
        raw_text,
        re.IGNORECASE,
    )
    if labelled:
        return _published_candidate(labelled.group(1))

    # 4. Semantic visible date/time near the article header.
    for element in soup.find_all(["time", "span", "div", "p"]):
        if element.find_parent(["h1", "h2", "title"]):
            continue
        marker = " ".join(
            [element.name or ""]
            + [str(element.get(key, "")) for key in ("class", "id", "itemprop", "data-role", "property")]
        ).lower()
        if any(word in marker for word in ("modified", "updated", "lastmod")):
            continue
        is_semantic_date = any(
            word in marker
            for word in ("datepublished", "publishdate", "published", "article__meta", "article-meta", "post-date", "news-info")
        ) or bool(re.search(r"(?:^|[^a-z0-9])(publish(?:ed)?|date|time)(?:[^a-z0-9]|$)", marker))
        if not is_semantic_date:
            continue
        value = element.get("content") or element.get("datetime") or element.get("title") or element.get_text(" ", strip=True)
        if len(str(value)) > 180:
            continue
        parsed = _published_candidate(value)
        if parsed:
            return parsed

    return None


class RawDocument(BaseModel):
    url: str
    source_id: str
    fetched_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    html: str
    text: str
    headers: Dict[str, str] = Field(default_factory=dict)
    status_code: int = 200
    snapshot_path: Optional[str] = None


class ParsedItem(BaseModel):
    url: str
    source_id: str
    title: str
    raw_content: str
    published_at: Optional[datetime.datetime] = None
    author: Optional[str] = None
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class SourceAdapter(ABC):
    """
    Abstract Base Class for Lead Source Adapters.
    Fetches rendered HTML through Crawl4AI with retries, rate limits, and raw
    snapshot persistence for auditability.
    """

    def __init__(
        self,
        source_id: str,
        name: str,
        seed_urls: List[str],
        rate_limit_delay: float = 1.0,
        timeout: int = 60,
    ):
        self.source_id = source_id
        self.name = name
        self.seed_urls = seed_urls
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout

    @abstractmethod
    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        """Discover live URLs from seed pages or search listings."""
        pass

    def _discovery_search_keywords(self, max_items: Optional[int] = None) -> List[str]:
        search_config = keyword_service.get_config().get("discovery_search", {})
        keywords = [
            normalize_unicode(str(value))
            for value in search_config.get("keywords", [])
            if normalize_unicode(str(value))
        ]
        max_queries = max(1, int(search_config.get("max_queries", 6)))
        if max_items:
            max_queries = min(max_queries, max_items)
        return keywords[:max_queries]

    async def discover_from_keyword_search(
        self,
        search_url_template: str,
        article_url_pattern: str,
        allowed_hosts: set[str],
        max_items: Optional[int] = None,
    ) -> List[str]:
        """Search a source by configured keywords and return verified article URLs.

        Search results are balanced across queries. A candidate must belong to an
        allowed host, match the source's article URL shape, and contain the query
        in its visible title/snippet. Full article content is still checked later.
        """
        keywords = self._discovery_search_keywords(max_items=max_items)
        if not keywords:
            return []

        per_query_limit = max(
            1,
            math.ceil((max_items or len(keywords) * 10) / len(keywords)),
        )
        found_urls: List[str] = []

        for keyword in keywords:
            search_url = search_url_template.format(query=quote_plus(keyword))
            try:
                raw_doc = await self.fetch(search_url)
                soup = BeautifulSoup(raw_doc.html, "html.parser")
                query_urls: List[str] = []

                for anchor in soup.find_all("a", href=True):
                    href = str(anchor.get("href") or "").strip()
                    if not href or href.startswith(("javascript:", "mailto:", "tel:")):
                        continue
                    if anchor.find_parent(["nav", "header", "footer", "aside"]):
                        continue
                    full_url = canonicalize_url(urljoin(search_url, href))
                    host = (urlparse(full_url).hostname or "").lower()
                    if host not in allowed_hosts or not re.search(article_url_pattern, full_url, re.IGNORECASE):
                        continue

                    context_node = anchor.find_parent(["article", "li"])
                    if context_node is None:
                        context_node = anchor.find_parent("div")
                    context = normalize_unicode(
                        (context_node or anchor).get_text(" ", strip=True)
                    ).lower()
                    if keyword.lower() not in context:
                        continue
                    if full_url in found_urls or full_url in query_urls:
                        continue

                    query_urls.append(full_url)
                    if len(query_urls) >= per_query_limit:
                        break

                found_urls.extend(query_urls)
                logger.info(
                    "[%s] Keyword search '%s' found %s candidate URLs",
                    self.source_id,
                    keyword,
                    len(query_urls),
                )
            except Exception as exc:
                logger.warning(
                    "[%s] Keyword search failed for '%s': %s",
                    self.source_id,
                    keyword,
                    exc,
                )

        return found_urls[:max_items] if max_items else found_urls

    async def fetch(self, url: str) -> RawDocument:
        """
        Render live HTML/JavaScript with Crawl4AI, then preserve the existing
        RawDocument contract used by discovery, parsing and the AI pipeline.
        """
        url = canonicalize_url(url)
        await asyncio.sleep(self.rate_limit_delay)

        last_error: Optional[Exception] = None

        for attempt in range(settings.max_retries + 1):
            try:
                page = await browser_crawl_service.fetch(
                    url,
                    timeout=self.timeout,
                    source_id=self.source_id,
                )
                clean_txt = clean_html(page.html)
                snapshot_path = self._save_snapshot(page.url, page.html)
                return RawDocument(
                    url=page.url,
                    source_id=self.source_id,
                    html=page.html,
                    text=clean_txt,
                    headers=page.headers,
                    status_code=page.status_code,
                    snapshot_path=str(snapshot_path),
                )

            except BackgroundPreemptedError:
                # Do not retry the same URL while FE owns priority. The next
                # background URL boundary will wait until FE is finished.
                raise
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                logger.warning(f"[{self.source_id}] Attempt {attempt + 1} failed for {url}: {e}")
                # If network is unreachable or host not found, fail fast instead of blocking
                if any(k in err_str for k in [
                    "network is unreachable", "nameresolutionerror", "connection refused",
                    "getaddrinfo", "http 400", "http 401", "http 403", "http 404",
                    "http 405", "http 410", "http 422",
                ]):
                    logger.info(f"[{self.source_id}] Host is unreachable ({e}), skipping further retries.")
                    break
                if attempt < settings.max_retries:
                    await asyncio.sleep(settings.retry_backoff_factor * (attempt + 1))

        raise RuntimeError(
            f"Failed to fetch {url} after {settings.max_retries + 1} attempts: {last_error}"
        )

    @abstractmethod
    async def parse(self, raw: RawDocument) -> ParsedItem:
        """Parse raw HTML document into a structured ParsedItem."""
        pass

    def _save_snapshot(self, url: str, html_content: str) -> Path:
        """Persist raw HTML snapshot for audit and replay."""
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        today_str = utc_now().strftime("%Y%m%d")
        snapshot_dir = RAW_DATA_DIR / self.source_id / today_str
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        file_path = snapshot_dir / f"{url_hash}.html"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

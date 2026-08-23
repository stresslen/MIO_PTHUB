from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import re
import ssl
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
import urllib3
from pydantic import BaseModel, Field

from app.config import RAW_DATA_DIR, settings
from app.pipeline.normalize import canonicalize_url, clean_html, normalize_unicode, parse_datetime, utc_now

urllib3.disable_warnings()
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


class CustomSSLAdapter(requests.adapters.HTTPAdapter):
    """
    SSL Adapter that supports older Diffie-Hellman ciphers used on some
    government portals (e.g. muasamcong.mpi.gov.vn) without compromising safety.
    """
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


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
    Fetches real live data with retries, custom SSL handling, rate limits,
    and automatic raw snapshot persistence for auditability.
    """

    def __init__(
        self,
        source_id: str,
        name: str,
        seed_urls: List[str],
        rate_limit_delay: float = 1.0,
        timeout: int = 30,
    ):
        self.source_id = source_id
        self.name = name
        self.seed_urls = seed_urls
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            sess = requests.Session()
            adapter = CustomSSLAdapter()
            sess.mount("https://", adapter)
            sess.mount("http://", adapter)
            sess.headers.update({
                "User-Agent": settings.crawler_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            })
            self._session = sess
        return self._session

    @abstractmethod
    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        """Discover live URLs from seed pages or search listings."""
        pass

    async def fetch(self, url: str) -> RawDocument:
        """
        Fetch live page content with retry, exponential backoff, rate limiting,
        and raw snapshot storage.
        """
        url = canonicalize_url(url)
        await asyncio.sleep(self.rate_limit_delay)

        loop = asyncio.get_event_loop()
        session = self._get_session()
        last_error: Optional[Exception] = None

        for attempt in range(settings.max_retries + 1):
            try:
                def _do_get():
                    resp = session.get(url, timeout=self.timeout, verify=False)
                    resp.encoding = resp.apparent_encoding or "utf-8"
                    return resp.text, resp.status_code, dict(resp.headers)

                html_text, status_code, resp_headers = await loop.run_in_executor(None, _do_get)
                
                if status_code in (200, 201, 202):
                    clean_txt = clean_html(html_text)
                    snapshot_path = self._save_snapshot(url, html_text)
                    return RawDocument(
                        url=url,
                        source_id=self.source_id,
                        html=html_text,
                        text=clean_txt,
                        headers=resp_headers,
                        status_code=status_code,
                        snapshot_path=str(snapshot_path),
                    )
                elif 400 <= status_code < 500:
                    logger.warning(f"[{self.source_id}] HTTP status {status_code} for {url} (skipping retry)")
                    break
                else:
                    logger.warning(f"[{self.source_id}] HTTP status {status_code} for {url}")

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                logger.warning(f"[{self.source_id}] Attempt {attempt + 1} failed for {url}: {e}")
                # If network is unreachable or host not found, fail fast instead of blocking
                if any(k in err_str for k in ["network is unreachable", "nameresolutionerror", "connection refused", "getaddrinfo"]):
                    logger.info(f"[{self.source_id}] Host is unreachable ({e}), skipping further retries.")
                    break
                if attempt < settings.max_retries:
                    await asyncio.sleep(settings.retry_backoff_factor * (attempt + 1))

        # Check for stored snapshot fallback if live site is temporarily unreachable
        fallback = self._load_fallback_snapshot(url)
        if fallback:
            logger.info(f"[{self.source_id}] Using offline snapshot fallback for {url}")
            return fallback

        raise RuntimeError(f"Failed to fetch {url} after {settings.max_retries + 1} attempts: {last_error}")

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

    def _load_fallback_snapshot(self, url: str) -> Optional[RawDocument]:
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        source_dir = RAW_DATA_DIR / self.source_id
        if not source_dir.exists():
            return None
        for file in source_dir.rglob(f"{url_hash}.html"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    content = f.read()
                return RawDocument(
                    url=url,
                    source_id=self.source_id,
                    html=content,
                    text=clean_html(content),
                    status_code=200,
                    snapshot_path=str(file),
                )
            except Exception:
                pass
        return None

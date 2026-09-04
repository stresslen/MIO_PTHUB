from __future__ import annotations

import datetime
import logging
import re
from typing import List, Optional
from bs4 import BeautifulSoup

from app.crawlers.base import SourceAdapter, RawDocument, ParsedItem, extract_published_at
from app.pipeline.normalize import parse_datetime, normalize_unicode, clean_html

logger = logging.getLogger(__name__)


class ChinhPhuAdapter(SourceAdapter):
    """
    Adapter for Cổng Thông tin điện tử Chính phủ (chinhphu.vn & baochinhphu.vn).
    Crawl policy decisions, investment programs, national digital transformation projects.
    """

    def __init__(self):
        super().__init__(
            source_id="chinhphu",
            name="Cổng Thông tin điện tử Chính phủ",
            seed_urls=[
                "https://chinhphu.vn/",
                "https://baochinhphu.vn/",
                "https://baochinhphu.vn/chi-dao-dieu-hanh.htm",
                "https://baochinhphu.vn/kinh-te.htm",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        found_urls: List[str] = []
        for seed_url in self.seed_urls:
            try:
                raw_doc = await self.fetch(seed_url)
                if not raw_doc or not raw_doc.html:
                    continue
                soup = BeautifulSoup(raw_doc.html, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    if re.search(r"-\d{10,20}\.htm$", href) or any(k in href for k in ["chi-dao", "quyet-dinh", "thoi-su", "chinh-sach"]):
                        full_url = href if href.startswith("http") else f"https://baochinhphu.vn{href}"
                        if full_url not in found_urls and len(full_url) > 30:
                            found_urls.append(full_url)
                            if max_items and len(found_urls) >= max_items:
                                break
            except Exception as e:
                logger.warning(f"[chinhphu] Discovery failed on {seed_url}: {e}")

            if max_items and len(found_urls) >= max_items:
                break

        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw.html, "html.parser")

        title_el = soup.find("h1", class_=lambda c: c and "title" in c.lower()) or soup.find("h1") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else "Báo Chính Phủ"
        title = re.sub(r"\s*-\s*Báo Chính phủ.*$", "", title, flags=re.IGNORECASE).strip()

        published_at = extract_published_at(soup, raw.text, title)

        content_el = soup.find("div", class_=lambda c: c and any(k in c.lower() for k in ["content", "detail", "body", "article"])) or soup.find("article")
        body_text = clean_html(raw.html)

        return ParsedItem(
            url=raw.url,
            source_id=self.source_id,
            title=title,
            raw_content=body_text,
            published_at=published_at,
            author=None,
            extra_metadata={},
        )


class XayDungChinhSachAdapter(SourceAdapter):
    """Adapter for Xây dựng Chính sách (xaydungchinhsach.chinhphu.vn)."""

    def __init__(self):
        super().__init__(
            source_id="xaydungchinhsach",
            name="Xây dựng Chính sách (chinhphu.vn)",
            seed_urls=[
                "https://xaydungchinhsach.chinhphu.vn/",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        found_urls: List[str] = []
        for seed_url in self.seed_urls:
            raw_doc = await self.fetch(seed_url)
            if not raw_doc or not raw_doc.html:
                continue
            soup = BeautifulSoup(raw_doc.html, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                if re.search(r"-\d+\.htm$", href) or "/tin-tuc/" in href:
                    full_url = href if href.startswith("http") else f"https://xaydungchinhsach.chinhphu.vn{href}"
                    if full_url not in found_urls and len(full_url) > 30:
                        found_urls.append(full_url)
                        if max_items and len(found_urls) >= max_items:
                            break
        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw.html, "html.parser")
        title_el = soup.find("h1") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else "Xây dựng Chính sách"
        title = re.sub(r"\s*-\s*Xây dựng chính sách.*$", "", title, flags=re.IGNORECASE).strip()

        published_at = extract_published_at(soup, raw.text, title)

        content_el = soup.find("div", class_=lambda c: c and "content" in c.lower()) or soup.find("article")
        body_text = clean_html(raw.html)

        return ParsedItem(
            url=raw.url,
            source_id=self.source_id,
            title=title,
            raw_content=body_text,
            published_at=published_at,
            author=None,
            extra_metadata={},
        )


class CongBaoAdapter(SourceAdapter):
    """Adapter for Công báo Chính phủ (congbao.chinhphu.vn)."""

    def __init__(self):
        super().__init__(
            source_id="congbao",
            name="Công báo Chính phủ",
            seed_urls=[
                "https://congbao.chinhphu.vn/",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        found_urls: List[str] = []
        for seed_url in self.seed_urls:
            raw_doc = await self.fetch(seed_url)
            if not raw_doc or not raw_doc.html:
                continue
            soup = BeautifulSoup(raw_doc.html, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                if re.search(r"/(?:van-ban|noi-dung|chi-tiet)/", href) or re.search(r"-\d+$", href):
                    full_url = href if href.startswith("http") else f"https://congbao.chinhphu.vn{href}"
                    if full_url not in found_urls and len(full_url) > 25:
                        found_urls.append(full_url)
                        if max_items and len(found_urls) >= max_items:
                            break
        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw.html, "html.parser")
        title_el = soup.find("h1") or soup.find("h2") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else "Công báo Chính phủ"
        title = re.sub(r"\s*-\s*Công báo.*$", "", title, flags=re.IGNORECASE).strip()

        published_at = extract_published_at(soup, raw.text, title)

        content_el = soup.find("div", class_=lambda c: c and "content" in c.lower()) or soup.find("article")
        body_text = clean_html(raw.html)

        return ParsedItem(
            url=raw.url,
            source_id=self.source_id,
            title=title,
            raw_content=body_text,
            published_at=published_at,
            author=None,
            extra_metadata={},
        )

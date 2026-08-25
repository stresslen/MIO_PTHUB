from __future__ import annotations

import datetime
import logging
import re
from typing import List, Optional
from bs4 import BeautifulSoup

from app.crawlers.base import SourceAdapter, RawDocument, ParsedItem, extract_published_at
from app.pipeline.normalize import parse_datetime, clean_html

logger = logging.getLogger(__name__)


class VietnamNetAdapter(SourceAdapter):
    """Adapter for VietnamNet ICT / Technology news."""

    def __init__(self):
        super().__init__(
            source_id="vietnamnet",
            name="VietnamNet (CNTT & CĐS)",
            seed_urls=[
                "https://vietnamnet.vn/thong-tin-truyen-thong",
                "https://vietnamnet.vn/cong-nghe",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        search_urls = await self.discover_from_keyword_search(
            search_url_template="https://vietnamnet.vn/tim-kiem?q={query}",
            article_url_pattern=r"https://vietnamnet\.vn/(?!video/).+-\d+\.html$",
            allowed_hosts={"vietnamnet.vn", "www.vietnamnet.vn"},
            max_items=max_items,
        )
        if search_urls:
            logger.info("[%s] Using keyword search discovery (%s URLs)", self.source_id, len(search_urls))
            return search_urls
        logger.warning("[%s] Search returned no verified URLs; using section discovery", self.source_id)

        found_urls: List[str] = []
        for seed in self.seed_urls:
            try:
                raw_doc = await self.fetch(seed)
                if not raw_doc or not raw_doc.html:
                    continue
                soup = BeautifulSoup(raw_doc.html, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    if re.search(r"-\d+\.html$", href) and not href.startswith("https://vietnamnet.vn/video"):
                        full_url = href if href.startswith("http") else f"https://vietnamnet.vn{href}"
                        if full_url not in found_urls and len(full_url) > 30:
                            found_urls.append(full_url)
                            if max_items and len(found_urls) >= max_items:
                                break
            except Exception as e:
                logger.warning(f"[{self.source_id}] Discovery error on {seed}: {e}")
        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw_doc: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw_doc.html, "html.parser")
        title_el = soup.find("h1") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else "VietnamNet Tin Công nghệ"
        title = re.sub(r"\s*-\s*VietNamNet.*$", "", title, flags=re.IGNORECASE).strip()

        published_at = extract_published_at(soup, raw_doc.text, title)

        content_el = soup.find("div", class_=lambda c: c and "maincontent" in c.lower()) or soup.find("article")
        body_text = clean_html(str(content_el)) if content_el else raw_doc.text

        return ParsedItem(
            url=raw_doc.url,
            source_id=self.source_id,
            title=title,
            raw_content=body_text[:5000],
            published_at=published_at,
            author=None,
            extra_metadata={},
        )


class VnExpressAdapter(SourceAdapter):
    """Adapter for VnExpress Số Hóa & Khoa học."""

    def __init__(self):
        super().__init__(
            source_id="vnexpress",
            name="VnExpress (Số Hóa & Khoa Học)",
            seed_urls=[
                "https://vnexpress.net/so-hoa",
                "https://vnexpress.net/khoa-hoc",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        search_urls = await self.discover_from_keyword_search(
            search_url_template="https://timkiem.vnexpress.net/?q={query}",
            article_url_pattern=r"https://vnexpress\.net/.+-\d+\.html$",
            allowed_hosts={"vnexpress.net", "www.vnexpress.net"},
            max_items=max_items,
        )
        if search_urls:
            logger.info("[%s] Using keyword search discovery (%s URLs)", self.source_id, len(search_urls))
            return search_urls
        logger.warning("[%s] Search returned no verified URLs; using section discovery", self.source_id)

        found_urls: List[str] = []
        for seed in self.seed_urls:
            try:
                raw_doc = await self.fetch(seed)
                if not raw_doc or not raw_doc.html:
                    continue
                soup = BeautifulSoup(raw_doc.html, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    if re.search(r"-\d+\.html$", href) and any(k in href for k in ["so-hoa", "khoa-hoc", "cong-nghe"]):
                        full_url = href if href.startswith("http") else f"https://vnexpress.net{href}"
                        if full_url not in found_urls and len(full_url) > 30:
                            found_urls.append(full_url)
                            if max_items and len(found_urls) >= max_items:
                                break
            except Exception as e:
                logger.warning(f"[{self.source_id}] Discovery error on {seed}: {e}")
        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw_doc: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw_doc.html, "html.parser")
        title_el = soup.find("h1", class_=lambda c: c and "title" in c.lower()) or soup.find("h1") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else "VnExpress Tin Số Hóa"
        title = re.sub(r"\s*-\s*VnExpress.*$", "", title, flags=re.IGNORECASE).strip()

        published_at = extract_published_at(soup, raw_doc.text, title)

        content_el = soup.find("article", class_=lambda c: c and "fck_detail" in c.lower()) or soup.find("article")
        body_text = clean_html(str(content_el)) if content_el else raw_doc.text

        return ParsedItem(
            url=raw_doc.url,
            source_id=self.source_id,
            title=title,
            raw_content=body_text[:5000],
            published_at=published_at,
            author=None,
            extra_metadata={},
        )


class MostGovAdapter(SourceAdapter):
    """Adapter for Bộ Khoa học và Công nghệ (mst.gov.vn)."""

    def __init__(self):
        super().__init__(
            source_id="most_gov",
            name="Bộ Khoa học và Công nghệ (mst.gov.vn)",
            seed_urls=[
                "https://mst.gov.vn/",
                "https://mst.gov.vn/tin-tuc-su-kien/chuyen-doi-so.htm",
                "https://mst.gov.vn/tin-tuc-su-kien/khoa-hoc-va-cong-nghe.htm",
                "https://mst.gov.vn/tin-tuc-su-kien/doi-moi-sang-tao.htm",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        search_urls = await self.discover_from_keyword_search(
            search_url_template="https://mst.gov.vn/tim-kiem.htm?keywords={query}",
            article_url_pattern=r"https://mst\.gov\.vn/.+-\d{8,}\.html?$",
            allowed_hosts={"mst.gov.vn", "www.mst.gov.vn"},
            max_items=max_items,
        )
        if search_urls:
            logger.info("[%s] Using keyword search discovery (%s URLs)", self.source_id, len(search_urls))
            return search_urls
        logger.warning("[%s] Search returned no verified URLs; using section discovery", self.source_id)

        found_urls: List[str] = []
        for seed in self.seed_urls:
            try:
                raw_doc = await self.fetch(seed)
                if not raw_doc or not raw_doc.html:
                    continue
                soup = BeautifulSoup(raw_doc.html, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    if any(k in href for k in ["tin-tuc", "thong-bao", "su-kien", "van-ban", "de-an", "chuyen-doi-so"]) or re.search(r"-\d+$", href) or href.endswith(".htm") or href.endswith(".html"):
                        if not href.startswith("javascript:") and not href.startswith("mailto:"):
                            full_url = href if href.startswith("http") else f"https://mst.gov.vn{href}"
                            if full_url not in found_urls and len(full_url) > 22 and full_url not in self.seed_urls:
                                found_urls.append(full_url)
                                if max_items and len(found_urls) >= max_items:
                                    break
            except Exception as e:
                logger.warning(f"[{self.source_id}] Discovery error on {seed}: {e}")
        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw_doc: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw_doc.html, "html.parser")
        title_el = soup.find("h1") or soup.find("h2") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else "Bộ Khoa học & Công nghệ"
        title = re.sub(r"\s*-\s*Bộ KH&CN.*$", "", title, flags=re.IGNORECASE).strip()

        published_at = extract_published_at(soup, raw_doc.text, title)

        content_el = soup.find("div", class_=lambda c: c and "content" in c.lower()) or soup.find("article")
        body_text = clean_html(str(content_el)) if content_el else raw_doc.text

        return ParsedItem(
            url=raw_doc.url,
            source_id=self.source_id,
            title=title,
            raw_content=body_text[:5000],
            published_at=published_at,
            author=None,
            extra_metadata={},
        )

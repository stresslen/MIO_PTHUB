from __future__ import annotations

import datetime
import logging
import re
from typing import List, Optional
from bs4 import BeautifulSoup

from app.crawlers.base import SourceAdapter, RawDocument, ParsedItem, extract_published_at
from app.pipeline.normalize import parse_datetime, clean_html

logger = logging.getLogger(__name__)


class DauThauAsiaAdapter(SourceAdapter):
    """
    Adapter for DauThau.info / dauthau.asia.
    Directly crawls live tender notices from https://dauthau.asia/thongbao/moithau/
    """

    def __init__(self):
        super().__init__(
            source_id="dauthau_asia",
            name="DauThau.info (dauthau.asia)",
            seed_urls=[
                "https://dauthau.asia/thongbao/moithau/",
                "https://dauthau.asia/thongbao/moithau/?page=2",
                "https://dauthau.asia/thongbao/moithau/?page=3",
                "https://dauthau.asia/news/",
                "https://dauthau.asia/",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        """
        Dynamically crawls ALL pagination pages from https://dauthau.asia/thongbao/moithau/
        as long as the tenders on that page fall within the timeframe (`since`).
        """
        found_urls: List[str] = []
        page = 1
        max_pages = 50  # Up to 50 pages of tender announcements (~1,000 tenders)

        while page <= max_pages:
            page_url = "https://dauthau.asia/thongbao/moithau/" if page == 1 else f"https://dauthau.asia/thongbao/moithau/?page={page}"
            logger.info(f"[{self.source_id}] Crawling page {page}: {page_url}")

            try:
                raw_doc = await self.fetch(page_url)
                if not raw_doc or not raw_doc.html:
                    break

                soup = BeautifulSoup(raw_doc.html, "html.parser")
                page_found = 0
                all_older_than_since = True

                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    is_candidate = (
                        "/thongbao/moithau/" in href
                        or "/tenders/" in href
                        or "/goi-thau/" in href
                        or "-tender-" in href
                        or re.search(r"/\d+-[^/]+\.html$", href)
                        or re.search(r"/procurement/[^/]+", href)
                    )

                    if is_candidate and href not in ["/thongbao/moithau/", "https://dauthau.asia/thongbao/moithau/", "#"] and not href.endswith("/thongbao/moithau/"):
                        full_url = href if href.startswith("http") else f"https://dauthau.asia{href}"

                        is_within_timeframe = True
                        if since:
                            parent = a_tag.find_parent(["tr", "li", "div", "article"])
                            if parent:
                                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", parent.get_text())
                                if date_match:
                                    item_dt = parse_datetime(date_match.group(1))
                                    if item_dt:
                                        if item_dt < since:
                                            is_within_timeframe = False
                                        else:
                                            all_older_than_since = False

                        if is_within_timeframe and full_url not in found_urls and "javascript:" not in full_url and len(full_url) > 28:
                            found_urls.append(full_url)
                            page_found += 1
                            if max_items and len(found_urls) >= max_items:
                                break

                # If no tender links found on this page, or all items are older than since, stop pagination
                if page_found == 0 and page > 1:
                    logger.info(f"[{self.source_id}] No more items on page {page}, stopping pagination.")
                    break
                if since and all_older_than_since and page > 2:
                    logger.info(f"[{self.source_id}] Reached tenders older than cutoff ({since}) on page {page}, stopping pagination.")
                    break

                if max_items and len(found_urls) >= max_items:
                    break

                page += 1

            except Exception as e:
                logger.warning(f"[{self.source_id}] Discovery error on page {page}: {e}")
                break

        # Also add news section if within limit
        if not max_items or len(found_urls) < max_items:
            try:
                news_doc = await self.fetch("https://dauthau.asia/news/")
                if news_doc and news_doc.html:
                    soup = BeautifulSoup(news_doc.html, "html.parser")
                    for a_tag in soup.find_all("a", href=True):
                        href = a_tag["href"].strip()
                        if "/news/" in href and href != "/news/" and not href.endswith("/news/"):
                            full_url = href if href.startswith("http") else f"https://dauthau.asia{href}"
                            if full_url not in found_urls and len(full_url) > 28:
                                found_urls.append(full_url)
                                if max_items and len(found_urls) >= max_items:
                                    break
            except Exception as ne:
                logger.warning(f"[{self.source_id}] News discovery error: {ne}")

        logger.info(f"[{self.source_id}] Discovered {len(found_urls)} live tender links across {page} pages from dauthau.asia")
        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw_doc: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw_doc.html, "html.parser")
        
        # 1. Title Extraction
        title_el = (
            soup.find("h1", class_=lambda c: c and any(k in c.lower() for k in ["title", "heading", "name"]))
            or soup.find("h1")
            or soup.find("title")
        )
        title = title_el.get_text(strip=True) if title_el else "Thông báo mời thầu - DauThau.info"
        title = re.sub(r"\s*-\s*DauThau\.info.*$", "", title, flags=re.IGNORECASE).strip()

        # 2. Date Extraction: accept only explicit publication evidence.
        published_at = extract_published_at(soup, raw_doc.text, title)

        # 3. Content Extraction (table details, bidding package summary)
        # Keep the original flattened text for labelled procurement fields before
        # removing navigation nodes from the article body.
        full_text = raw_doc.text

        # Decompose non-content boilerplate elements
        for tag in soup(["header", "footer", "nav", "aside", "script", "style", "noscript"]):
            tag.decompose()
        for el in soup.find_all(class_=lambda c: c and any(k in c.lower() for k in ["menu", "header", "footer", "sidebar", "banner", "breadcrumb", "social", "comment", "nav", "feedback"])):
            el.decompose()

        content_el = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=lambda c: c and any(k in c.lower() for k in ["tender-detail", "package-detail", "detail-content"]))
            or soup.find("body")
        )
        body_text = clean_html(str(content_el)) if content_el else full_text

        # Preserve high-value procurement fields before truncating content for Gemini.
        # DauThau.info pages contain long menus before the actual tender details.
        structured_lines = []
        field_patterns = [
            ("Chủ đầu tư", r"Chủ đầu tư\s+(.{4,300}?)\s+Mã KHLCNT\b"),
            ("Bên mời thầu", r"Bên mời thầu\s+(.{4,300}?)\s+(?:Mã|Tên|Địa chỉ)\b"),
            ("Tên dự án", r"Tên dự án\s+(.{4,400}?)\s+Tên gói thầu\b"),
            ("Tên gói thầu", r"Tên gói thầu\s+(.{4,400}?)\s+(?:Chủ đầu tư|Bên mời thầu|Mã TBMT|Số TBMT|Phân loại KHLCNT)\b"),
            ("Cơ quan phê duyệt", r"Cơ quan ra quyết định phê duyệt\s+(.{4,300}?)\s+(?:Quyết định|Thời điểm|Ngày)\b"),
        ]
        for label, pattern in field_patterns:
            for match in re.finditer(pattern, full_text, re.IGNORECASE):
                value = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
                if value and not re.search(r"Bảng giá|Danh sách|TOP 10|không tìm được", value, re.IGNORECASE):
                    structured_lines.append(f"{label}: {value}")
                    break
        if published_at:
            structured_lines.append(f"Ngày đăng: {published_at.strftime('%d/%m/%Y %H:%M')}")

        enriched_content = "\n".join(structured_lines + [body_text])

        return ParsedItem(
            url=raw_doc.url,
            source_id=self.source_id,
            title=title,
            raw_content=enriched_content[:5000],
            published_at=published_at,
            author=None,
            extra_metadata={},
        )

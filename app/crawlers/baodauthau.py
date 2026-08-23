from __future__ import annotations

import datetime
import logging
import re
from typing import List, Optional
from bs4 import BeautifulSoup

from app.crawlers.base import SourceAdapter, RawDocument, ParsedItem, extract_published_at
from app.pipeline.normalize import parse_datetime, clean_html

logger = logging.getLogger(__name__)


class BaoDauThauAdapter(SourceAdapter):
    """
    Adapter for Báo Đấu thầu (baodauthau.vn).
    Crawl directly from https://baodauthau.vn/thong-bao-moi-thau/
    Supports filtering by timeframe (since).
    """

    def __init__(self):
        super().__init__(
            source_id="baodauthau",
            name="Báo Đấu thầu",
            seed_urls=[
                "https://baodauthau.vn/thong-bao-moi-thau/",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        """
        Discover tender notice links from https://baodauthau.vn/thong-bao-moi-thau/
        Filters by `since` if provided.
        """
        found_urls: List[str] = []

        for seed in self.seed_urls:
            raw_doc = await self.fetch(seed)
            if not raw_doc or not raw_doc.html:
                continue

            try:
                soup = BeautifulSoup(raw_doc.html, "html.parser")
                
                # Look for tender notice article links: post\d+\.html or /thong-bao-moi-thau/
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    
                    is_tender_link = (
                        re.search(r"-post\d+\.html", href)
                        or "/thong-bao-moi-thau/" in href
                        or re.search(r"/(?:goi-thau|du-an|moi-thau)/", href)
                    )

                    if is_tender_link and href != "/thong-bao-moi-thau/" and href != "https://baodauthau.vn/thong-bao-moi-thau/":
                        full_url = href if href.startswith("http") else f"https://baodauthau.vn{href}"
                        
                        # Check adjacent date if present
                        if since:
                            parent = a_tag.find_parent(["article", "div", "li", "tr"])
                            if parent:
                                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", parent.get_text())
                                if date_match:
                                    item_dt = parse_datetime(date_match.group(1))
                                    if item_dt and item_dt < since:
                                        continue

                        if full_url not in found_urls and len(full_url) > 30:
                            found_urls.append(full_url)
                            if max_items and len(found_urls) >= max_items:
                                break

            except Exception as e:
                logger.error(f"[{self.source_id}] Discovery error on {seed}: {e}")

        logger.info(f"[{self.source_id}] Discovered {len(found_urls)} tender notice links from {self.seed_urls[0]}")
        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw_doc: RawDocument) -> ParsedItem:
        """
        Parse tender notice or article from Báo Đấu thầu.
        """
        soup = BeautifulSoup(raw_doc.html, "html.parser")

        # 1. Title
        title_el = (
            soup.find("h1", class_=lambda c: c and "title" in c.lower())
            or soup.find("h1")
            or soup.find("title")
        )
        title = title_el.get_text(strip=True) if title_el else "Thông báo mời thầu - Báo Đấu thầu"
        title = re.sub(r"\s*-\s*Báo Đấu thầu.*$", "", title, flags=re.IGNORECASE).strip()

        # 2. Published Date: metadata only; never infer from title/body dates.
        published_at = extract_published_at(soup, raw_doc.text, title)

        # 3. Content
        content_el = (
            soup.find("div", class_=lambda c: c and any(k in c.lower() for k in ["content", "detail", "body", "article"]))
            or soup.find("article")
            or soup.find("main")
        )
        body_text = clean_html(str(content_el)) if content_el else raw_doc.text

        # 4. Meta Description & Keywords
        meta_desc = soup.find("meta", attrs={"name": "description"})
        description = meta_desc.get("content", "").strip() if meta_desc else ""

        return ParsedItem(
            url=raw_doc.url,
            source_id=self.source_id,
            title=title,
            raw_content=f"{description}\n{body_text}",
            published_at=published_at,
            author=None,
            extra_metadata={},
        )

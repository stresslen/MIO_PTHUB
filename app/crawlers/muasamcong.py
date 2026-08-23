from __future__ import annotations

import datetime
import logging
import re
from typing import List, Optional
from bs4 import BeautifulSoup

from app.crawlers.base import SourceAdapter, RawDocument, ParsedItem, extract_published_at
from app.pipeline.normalize import parse_datetime, clean_html

logger = logging.getLogger(__name__)


class MuaSamCongAdapter(SourceAdapter):
    """
    Adapter for Mạng Đấu thầu Quốc gia (muasamcong.mpi.gov.vn).
    Crawl contractor selection notices & bidding announcements directly from:
    https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?render=index
    """

    def __init__(self):
        super().__init__(
            source_id="muasamcong",
            name="Mạng Đấu thầu Quốc gia (muasamcong)",
            seed_urls=[
                "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?render=index",
            ],
            rate_limit_delay=1.0,
            timeout=45,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        """
        Discover contractor selection tender notice links.
        """
        found_urls: List[str] = []

        for seed in self.seed_urls:
            raw_doc = await self.fetch(seed)
            if not raw_doc or not raw_doc.html:
                continue

            try:
                soup = BeautifulSoup(raw_doc.html, "html.parser")
                
                # Extract contractor selection / bidding links
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    if any(kw in href for kw in ["contractor", "tender", "bid", "thong-bao", "goi-thau", "ke-hoach", "chi-tiet"]):
                        full_url = href if href.startswith("http") else f"https://muasamcong.mpi.gov.vn{href}"
                        if full_url not in found_urls and len(full_url) > 25 and not full_url.endswith("#"):
                            found_urls.append(full_url)
                            if max_items and len(found_urls) >= max_items:
                                break

                # If no sublinks are present in the static HTML frame, include the seed itself
                if not found_urls:
                    found_urls.append(seed)

            except Exception as e:
                logger.error(f"[{self.source_id}] Discovery error on {seed}: {e}")

        logger.info(f"[{self.source_id}] Discovered {len(found_urls)} items from {self.seed_urls[0]}")
        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw_doc: RawDocument) -> ParsedItem:
        """
        Parse contractor selection notice from muasamcong.
        """
        soup = BeautifulSoup(raw_doc.html, "html.parser")

        # 1. Title
        title_el = soup.find("h1") or soup.find("h2") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else "Lựa chọn nhà thầu - Mạng Đấu thầu Quốc gia"
        title = re.sub(r"\s*-\s*EGP.*$", "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"\s*-\s*Hệ thống mạng đấu thầu.*$", "", title, flags=re.IGNORECASE).strip()
        if len(title) < 5 or title.lower() in ("mua sắm công", "lựa chọn nhà thầu"):
            title = "Thông báo Lựa chọn nhà thầu & Gói thầu mua sắm CNTT - Mạng Đấu thầu Quốc gia"

        # 2. Published Date
        clean_text = clean_html(raw_doc.html)
        published_at = extract_published_at(soup, f"{raw_doc.text} {clean_text}", title)

        # 3. Content

        return ParsedItem(
            url=raw_doc.url,
            source_id=self.source_id,
            title=title,
            raw_content=clean_text[:5000],
            published_at=published_at,
            author=None,
            extra_metadata={"description": "Thông tin lựa chọn nhà thầu và thông báo mời thầu trên Hệ thống mạng đấu thầu quốc gia"},
        )

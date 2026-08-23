from __future__ import annotations

import datetime
import logging
import re
from typing import List, Optional
from bs4 import BeautifulSoup

from app.crawlers.base import SourceAdapter, RawDocument, ParsedItem, extract_published_at
from app.pipeline.normalize import parse_datetime, normalize_unicode

logger = logging.getLogger(__name__)


class HanoiGovAdapter(SourceAdapter):
    """
    Adapter for Cổng Thông tin điện tử TP. Hà Nội (hanoi.gov.vn).
    Crawl Hanoi government procurement, digital government initiatives, and directives.
    """

    def __init__(self):
        super().__init__(
            source_id="hanoi_gov",
            name="Cổng Thông tin điện tử TP. Hà Nội",
            seed_urls=[
                "https://hanoi.gov.vn",
                "https://hanoi.gov.vn/tin-tuc-su-kien-noi-bat",
                "https://hanoi.gov.vn/chi-dao-dieu-hanh",
            ],
            rate_limit_delay=1.0,
            timeout=30,
        )

    async def discover(self, since: Optional[datetime.datetime] = None, max_items: Optional[int] = None) -> List[str]:
        found_urls: List[str] = []
        for seed_url in self.seed_urls:
            try:
                raw_doc = await self.fetch(seed_url)
                soup = BeautifulSoup(raw_doc.html, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    # Match news, articles, or directives on Hanoi portal
                    if re.search(r"(?:tin-tuc|chi-tiet|van-ban|thong-tin|su-kien|chi-dao)", href) and (href.endswith(".htm") or href.endswith(".html") or re.search(r"-\d+$", href)):
                        full_url = href if href.startswith("http") else f"https://hanoi.gov.vn{href}"
                        if full_url not in found_urls and len(full_url) > 30:
                            found_urls.append(full_url)
                            if max_items and len(found_urls) >= max_items:
                                break
            except Exception as e:
                logger.warning(f"[hanoi_gov] Discovery failed on {seed_url}: {e}")

            if max_items and len(found_urls) >= max_items:
                break

        return found_urls[:max_items] if max_items else found_urls

    async def parse(self, raw: RawDocument) -> ParsedItem:
        soup = BeautifulSoup(raw.html, "html.parser")

        # 1. Title
        title = ""
        h1 = soup.find("h1") or soup.find(class_=re.compile(r"title|heading-detail", re.I))
        if h1:
            title = normalize_unicode(h1.get_text())
        if not title:
            meta_t = soup.find("meta", property="og:title")
            title = normalize_unicode(meta_t["content"] if meta_t else soup.title.string if soup.title else "")

        # 2. Date
        pub_date = extract_published_at(soup, raw.text, title)

        # 3. Content: select the article body before generic containers such as
        # search-content, otherwise Gemini receives navigation text instead of the article.
        body_parts = []
        sapo = soup.find(attrs={"data-role": "sapo"}) or soup.find(class_=re.compile(r"news-sapo|article-sapo", re.I))
        if sapo:
            sapo_text = normalize_unicode(sapo.get_text(" "))
            if len(sapo_text) > 20:
                body_parts.append(sapo_text)

        content_box = (
            soup.find(attrs={"data-role": "content"})
            or soup.find(class_=re.compile(r"detail-content|article-body|cms-body|news-content", re.I))
            or soup.find("article")
            or soup.find("main")
        )
        if content_box:
            for el in content_box.find_all(["p", "h2", "h3", "li"]):
                txt = normalize_unicode(el.get_text(" "))
                if txt and len(txt) > 20 and txt not in body_parts:
                    body_parts.append(txt)

        full_content = "\n\n".join(body_parts) if body_parts else raw.text

        return ParsedItem(
            url=raw.url,
            source_id=self.source_id,
            title=title or "Thông tin TP. Hà Nội",
            raw_content=full_content,
            published_at=pub_date,
            extra_metadata={"source": "hanoi.gov.vn", "location": "Hà Nội"},
        )

#!/usr/bin/env python3
"""Test TopCV with fresh browser vs existing profile."""

import asyncio
import os
import shutil
import tempfile
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

TARGET_URL = "https://www.topcv.vn/tim-viec-lam-so-hoa?type_keyword=1&sba=1"

async def test_fresh():
    print("Testing with completely FRESH browser...")
    browser_cfg = BrowserConfig(
        browser_type="chromium",
        headless=True,
        verbose=False,
    )
    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="commit",
        page_timeout=30_000,
        delay_before_return_html=3.0,
    )
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        res = await crawler.arun(url=TARGET_URL, config=run_cfg)
        print(f"  FRESH BROWSER -> Success: {res.success}, Status: {res.status_code}, HTML Length: {len(res.html) if res.html else 0}")
        return res.success

if __name__ == "__main__":
    asyncio.run(test_fresh())

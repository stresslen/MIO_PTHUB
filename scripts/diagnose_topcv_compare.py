#!/usr/bin/env python3
"""Compare crawl configs on TopCV: wait_until='commit' vs default/domcontentloaded."""

import asyncio
import os
import sys
from pathlib import Path

TARGET_URL = "https://www.topcv.vn/tim-viec-lam-so-hoa?type_keyword=1&sba=1"

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

async def test_config(name: str, wait_until_val: str, delay: float):
    print(f"\n--- Testing with wait_until='{wait_until_val}', delay={delay}s ---")
    browser_cfg = BrowserConfig(
        browser_type="chromium",
        headless=True,
        verbose=False,
    )
    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until=wait_until_val,
        page_timeout=30_000,
        delay_before_return_html=delay,
    )
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        res = await crawler.arun(url=TARGET_URL, config=run_cfg)
        print(f"  [{name}] Success: {res.success}")
        print(f"  [{name}] Status Code: {res.status_code}")
        print(f"  [{name}] Error Message: {res.error_message}")
        print(f"  [{name}] HTML Length: {len(res.html) if res.html else 0} bytes")
        if res.html and len(res.html) < 10000:
            print(f"  [{name}] HTML snippet: {res.html[:250]}")

async def main():
    # Test 1: Exactly like topcv.py (wait_until="commit", delay=3.0)
    await test_config("TOPCV_PY_CURRENT (commit)", wait_until_val="commit", delay=3.0)

    # Test 2: With domcontentloaded
    await test_config("DOMCONTENTLOADED", wait_until_val="domcontentloaded", delay=3.0)

if __name__ == "__main__":
    asyncio.run(main())

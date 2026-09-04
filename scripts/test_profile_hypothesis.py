#!/usr/bin/env python3
"""Test if the persistent profile directory is causing HTTP 403."""

import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

TARGET_URL = "https://www.topcv.vn/tim-viec-lam-so-hoa?type_keyword=1&sba=1"
PROFILE_PATH = "/home/reg/DATLD/MIO/profiles/topcv-zero-delay-85a680ccf2e2607e"

async def test_with_profile():
    print(f"\n--- Testing WITH persistent profile: {PROFILE_PATH} ---")
    browser_cfg = BrowserConfig(
        browser_type="chromium",
        headless=True,
        java_script_enabled=True,
        use_persistent_context=True,
        user_data_dir=PROFILE_PATH,
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
        print(f"  Result with profile: Success={res.success}, Status={res.status_code}, Error={res.error_message}")
        if res.html:
            print(f"  HTML Length: {len(res.html)}")

if __name__ == "__main__":
    asyncio.run(test_with_profile())

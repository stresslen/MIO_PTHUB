#!/usr/bin/env python3
"""Standalone diagnostic script for TopCV anti-bot response - does NOT modify project code."""

import asyncio
import os
import sys
from pathlib import Path
import requests

TARGET_URL = "https://www.topcv.vn/tim-viec-lam-so-hoa?type_keyword=1&sba=1"

print("=" * 65)
print("TEST RIÊNG TOPCV ANTI-BOT & HTTP 403")
print("Target URL:", TARGET_URL)
print("=" * 65)

# 1. Test standard HTTP GET with normal browser headers
print("\n[1] Thử nghiệm HTTP GET thông thường (Requests with Chrome User-Agent)...")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.topcv.vn/",
}

try:
    resp = requests.get(TARGET_URL, headers=headers, timeout=15)
    print(f"    -> HTTP Status: {resp.status_code}")
    print(f"    -> Content-Type: {resp.headers.get('Content-Type')}")
    print(f"    -> Server: {resp.headers.get('Server')}")
    print(f"    -> CF-Ray: {resp.headers.get('cf-ray')}")
    print(f"    -> Độ dài nội dung: {len(resp.text)} bytes")
    print(f"    -> 300 ký tự đầu của HTML:")
    print(resp.text[:300])
except Exception as e:
    print(f"    -> Ngoại lệ: {e}")

# 2. Test Crawl4AI browser if available
print("\n[2] Thử nghiệm Crawl4AI Playwright Browser...")
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

    async def run_crawl4ai():
        browser_cfg = BrowserConfig(
            browser_type="chromium",
            headless=True,
            verbose=False,
        )
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            delay_before_return_html=3.0,
        )
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            res = await crawler.arun(url=TARGET_URL, config=run_cfg)
            print(f"    -> Crawl4AI Success: {res.success}")
            print(f"    -> Crawl4AI Status Code: {res.status_code}")
            print(f"    -> Crawl4AI Error Message: {res.error_message}")
            if res.html:
                print(f"    -> HTML length: {len(res.html)} bytes")
                # Check for anti-bot indicators
                indicators = ["cloudflare", "just a moment", "challenge", "turnstile", "captcha", "datadome", "403 forbidden", "access denied"]
                found = [ind for ind in indicators if ind in res.html.lower()]
                print(f"    -> Dấu hiệu Anti-bot trong HTML: {found}")
                print(f"    -> Preview HTML:")
                print(res.html[:400])

    asyncio.run(run_crawl4ai())
except Exception as e:
    print(f"    -> Crawl4AI test error: {e}")

print("\n" + "=" * 65)
print("KẾT THÚC TEST RIÊNG TOPCV")
print("=" * 65)

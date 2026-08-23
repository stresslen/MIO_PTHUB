#!/usr/bin/env python3
"""
CLI Tool to execute Live Crawl & Pipeline Processing directly from Terminal.
Usage:
  python3 -m scripts.run_crawler --source baodauthau --max 10 --timeframe 1w
  python3 -m scripts.run_crawler --all --max 15 --timeframe 1m
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import init_db
from app.services.crawler_service import crawler_service
from app.crawlers import CRAWLER_REGISTRY


async def main():
    parser = argparse.ArgumentParser(description="AI Lead Intelligence & Crawler CLI")
    parser.add_argument("--source", type=str, choices=list(CRAWLER_REGISTRY.keys()), help="Source ID to crawl")
    parser.add_argument("--all", action="store_true", help="Crawl all registered sources")
    parser.add_argument("--max", type=int, default=15, help="Max URLs to discover per source")
    parser.add_argument("--timeframe", type=str, default="1_week", choices=["1_day", "1d", "1_week", "1w", "1_month", "1m", "all"], help="Timeframe filter for articles (1_day, 1_week, 1_month, all)")
    parser.add_argument("--force", action="store_true", help="Force re-crawl and re-process duplicate items")

    args = parser.parse_args()

    init_db()

    print("=" * 70)
    print("🚀 AI Lead Intelligence & Crawler - Live Pipeline Execution")
    print(f"[*] Timeframe Filter: {args.timeframe}")
    print("=" * 70)

    if args.all or not args.source:
        print(f"[*] Crawling ALL active sources (max {args.max} items/source)...")
        runs = await crawler_service.run_all_sources(force_recrawl=args.force, max_items=args.max, timeframe=args.timeframe)
        for r in runs:
            print(f"  -> [{r.source}] Status: {r.status} | Discovered: {r.total_discovered} | New Leads: {r.new_leads} | Duplicates: {r.duplicate_leads} | Errors: {r.error_count}")
    else:
        print(f"[*] Crawling source '{args.source}' (max {args.max} items)...")
        run = await crawler_service.run_crawler_for_source(args.source, force_recrawl=args.force, max_items=args.max, timeframe=args.timeframe)
        print(f"  -> [{run.source}] Status: {run.status} | Discovered: {run.total_discovered} | New Leads: {run.new_leads} | Duplicates: {run.duplicate_leads} | Errors: {run.error_count}")

    print("\n✅ Execution completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())

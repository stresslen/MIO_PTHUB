#!/usr/bin/env python3
"""
Dedicated Automated Daily Scheduler Daemon for AI Lead Intelligence & Crawler.
Usage:
  python3 -m scripts.auto_scheduler --bootstrap
  python3 -m scripts.auto_scheduler --run-now
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import init_db
from app.services.scheduler_service import scheduler_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler_daemon")


async def main():
    parser = argparse.ArgumentParser(description="AI Lead Intelligence Daily Scheduler Daemon")
    parser.add_argument("--bootstrap", action="store_true", help="Crawl historical data (past 1 month) immediately on start")
    parser.add_argument("--run-now", action="store_true", help="Run full crawl immediately then exit")
    parser.add_argument("--timeframe", type=str, default="1_month", help="Timeframe for immediate run (1_day, 1_week, 1_month, all)")

    args = parser.parse_args()

    init_db()

    print("=" * 75)
    print("⏰ AI Lead Intelligence - Automated Scheduler Daemon")
    print("=" * 75)

    if args.run_now:
        print(f"[*] Executing immediate crawl across all 10 sources (Timeframe: {args.timeframe})...")
        res = await scheduler_service.trigger_immediate_run(timeframe=args.timeframe, max_items=25)
        print(f"✅ Immediate run finished: {res}")
        return

    print("[*] Starting continuous daily background scheduler loop...")
    scheduler_service.start(auto_bootstrap=args.bootstrap)

    try:
        # Keep running
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        print("\n[!] Stopping scheduler daemon...")
        scheduler_service.stop()


if __name__ == "__main__":
    asyncio.run(main())

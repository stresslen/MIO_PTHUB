#!/usr/bin/env python3
"""Dedicated crawl worker.

This is the only process allowed to run crawl/browser/AI/Google Sheets pipeline
work. FastAPI only enqueues jobs in the shared database.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import init_db
from app.models.source import CrawlJobRead, CrawlJobStatusEnum
from app.services.browser_crawl_service import browser_crawl_service
from app.services.crawl_job_service import crawl_job_service
from app.services.crawler_service import crawler_service
from app.services.keyword_service import keyword_service
from app.services.scheduler_state_service import scheduler_state_service
from app.services.source_service import source_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawl_worker")


class CrawlWorker:
    def __init__(self, poll_interval: float = 1.0) -> None:
        self.poll_interval = max(0.25, poll_interval)
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._stop = asyncio.Event()
        self._current_task: asyncio.Task | None = None
        self._current_job_id: str | None = None

    def request_stop(self) -> None:
        self._stop.set()

    async def bootstrap(self) -> None:
        init_db()
        scheduler_state_service.load_persistent_config_for_worker()
        try:
            await asyncio.to_thread(keyword_service.bootstrap)
        except Exception:
            logger.exception("[Worker] Không thể đồng bộ Keywords; dùng cache hiện có")
        try:
            await asyncio.to_thread(source_service.bootstrap)
        except Exception:
            logger.exception("[Worker] Không thể đồng bộ Sources; dùng cache hiện có")
        recovered_runs = await crawler_service.recover_interrupted_runs()
        recovered_jobs = await asyncio.to_thread(crawl_job_service.recover_interrupted_jobs)
        if recovered_runs or recovered_jobs:
            logger.warning(
                "[Worker] Phục hồi %s crawl run và đưa lại %s job vào hàng đợi",
                recovered_runs,
                recovered_jobs,
            )

    async def _refresh_runtime_inputs(self) -> None:
        try:
            await asyncio.to_thread(source_service.refresh)
        except Exception:
            logger.exception("[Worker] Không thể refresh Sources; tiếp tục với cache gần nhất")
        try:
            await asyncio.to_thread(keyword_service.refresh)
        except Exception:
            logger.exception("[Worker] Không thể refresh Keywords; tiếp tục với cache gần nhất")

    @staticmethod
    def _summarize(runs) -> tuple[CrawlJobStatusEnum, dict]:
        run_items = [
            {
                "id": run.id,
                "source": run.source,
                "status": run.status,
                "total_discovered": run.total_discovered or 0,
                "new_leads": run.new_leads or 0,
                "duplicate_leads": run.duplicate_leads or 0,
                "filtered_out": run.filtered_out or 0,
                "error_count": run.error_count or 0,
                "error_message": run.error_message,
            }
            for run in runs
        ]
        statuses = {item["status"] for item in run_items}
        if run_items and statuses == {"FAILED"}:
            status = CrawlJobStatusEnum.FAILED
        elif "FAILED" in statuses or "PARTIAL" in statuses:
            status = CrawlJobStatusEnum.PARTIAL
        else:
            status = CrawlJobStatusEnum.SUCCESS
        result = {
            "status": status.value,
            "sources": len(run_items),
            "total_discovered": sum(item["total_discovered"] for item in run_items),
            "new_leads": sum(item["new_leads"] for item in run_items),
            "duplicate_leads": sum(item["duplicate_leads"] for item in run_items),
            "filtered_out": sum(item["filtered_out"] for item in run_items),
            "error_count": sum(item["error_count"] for item in run_items),
            "runs": run_items,
        }
        return status, result

    async def execute(self, job: CrawlJobRead) -> None:
        logger.info(
            "[Worker] Bắt đầu job %s (source=%s, timeframe=%s, trigger=%s)",
            job.id,
            job.source_id or "all",
            job.timeframe,
            job.trigger,
        )
        try:
            await self._refresh_runtime_inputs()
            manual = job.trigger != "SCHEDULE"
            if job.source_id:
                run = await crawler_service.run_crawler_for_source(
                    source_id=job.source_id,
                    force_recrawl=job.force_recrawl,
                    timeframe=job.timeframe,
                    is_manual_fe=manual,
                    job_id=job.id,
                )
                runs = [run]
            else:
                runs = await crawler_service.run_all_sources(
                    force_recrawl=job.force_recrawl,
                    timeframe=job.timeframe,
                    is_manual_fe=manual,
                    job_id=job.id,
                )
            status, result = self._summarize(runs)
            await asyncio.to_thread(
                crawl_job_service.finish,
                job.id,
                status=status,
                result=result,
            )
            if job.trigger == "SCHEDULE":
                await asyncio.to_thread(scheduler_state_service.record_scheduled_result, result)
            logger.info(
                "[Worker] Hoàn tất job %s: %s liên kết, +%s lead, status=%s",
                job.id,
                result["total_discovered"],
                result["new_leads"],
                status.value,
            )
        except asyncio.CancelledError:
            logger.warning("[Worker] Job %s bị ngắt khi worker dừng", job.id)
            raise
        except Exception as exc:
            logger.exception("[Worker] Job %s thất bại", job.id)
            result = {
                "status": CrawlJobStatusEnum.FAILED.value,
                "sources": 0,
                "total_discovered": 0,
                "new_leads": 0,
                "error_count": 1,
            }
            await asyncio.to_thread(
                crawl_job_service.finish,
                job.id,
                status=CrawlJobStatusEnum.FAILED,
                result=result,
                error_message=str(exc),
            )
            if job.trigger == "SCHEDULE":
                await asyncio.to_thread(scheduler_state_service.record_scheduled_result, result)

    async def run(self, *, once: bool = False) -> None:
        await self.bootstrap()
        logger.info("[Worker] Online với id=%s", self.worker_id)
        try:
            while not self._stop.is_set():
                await asyncio.to_thread(scheduler_state_service.heartbeat)
                await asyncio.to_thread(scheduler_state_service.sync_dirty_config_to_sheets)
                scheduled_job_id = await asyncio.to_thread(scheduler_state_service.enqueue_due_job)
                if scheduled_job_id:
                    logger.info("[Scheduler] Đã xếp job tự động %s", scheduled_job_id)

                if self._current_task is None:
                    job = await asyncio.to_thread(
                        crawl_job_service.claim_next,
                        self.worker_id,
                    )
                    if job is not None:
                        self._current_job_id = job.id
                        self._current_task = asyncio.create_task(
                            self.execute(job),
                            name=f"crawl-job-{job.id}",
                        )
                    elif once:
                        return
                elif self._current_task.done():
                    await self._current_task
                    self._current_task = None
                    self._current_job_id = None
                    if once:
                        return
                else:
                    if self._current_job_id:
                        job_status = await asyncio.to_thread(
                            crawl_job_service.get_job_status, self._current_job_id
                        )
                        if job_status is None or job_status in (
                            CrawlJobStatusEnum.INTERRUPTED.value,
                            CrawlJobStatusEnum.FAILED.value,
                        ):
                            logger.warning(
                                "[Worker] Lệnh hủy/xóa nhận được cho job %s (status=%s). Đang hủy tác vụ...",
                                self._current_job_id,
                                job_status or "DELETED",
                            )
                            self._current_task.cancel()
                            try:
                                await self._current_task
                            except (asyncio.CancelledError, Exception):
                                pass
                            self._current_task = None
                            self._current_job_id = None
                            await browser_crawl_service.close()

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()
                await asyncio.gather(self._current_task, return_exceptions=True)
            await browser_crawl_service.close()
            logger.info("[Worker] Đã dừng")


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="MIO dedicated crawl worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job then exit")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Queue a manual all-source crawl before starting",
    )
    parser.add_argument(
        "--timeframe",
        choices=["1_day", "1_week", "1_month"],
        default="1_week",
    )
    args = parser.parse_args()

    init_db()
    if args.run_now:
        queued = crawl_job_service.enqueue(
            source_id=None,
            timeframe=args.timeframe,
            force_recrawl=False,
            trigger="CLI",
        )
        logger.info("[Worker] Đã xếp job CLI %s", queued.id)

    worker = CrawlWorker(poll_interval=args.poll_interval)
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, worker.request_stop)
        except NotImplementedError:
            pass
    await worker.run(once=args.once)


if __name__ == "__main__":
    asyncio.run(async_main())

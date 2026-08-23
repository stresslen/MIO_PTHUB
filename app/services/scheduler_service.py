from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.config import settings
from app.database import SessionLocal
from app.models.lead import Lead
from app.pipeline.normalize import utc_now
from app.services.crawler_service import crawler_service
from app.services.google_sheets_service import google_sheets_service
from app.services.priority_service import priority_coordinator

logger = logging.getLogger(__name__)


class SchedulerService:
    """Configurable in-process crawler scheduler for a single Render worker."""

    def __init__(self) -> None:
        self.enabled = settings.scheduler_enabled
        self.timezone = settings.scheduler_timezone
        self.cadence = "daily"
        self.hour = settings.scheduler_hour
        self.minute = settings.scheduler_minute
        self.timeframe = "1_day"
        self.max_items: Optional[int] = None
        self.bootstrap_done = False
        self.is_running = False
        self.current_task: Optional[asyncio.Task] = None
        self.last_run_at: Optional[datetime.datetime] = None
        self.next_run_at: Optional[datetime.datetime] = None
        self.total_automated_runs = 0
        self.last_run_summary: Dict[str, Any] = {
            "status": "IDLE", "new_leads": 0, "total_discovered": 0, "error_count": 0
        }

    def _config_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "timezone": self.timezone,
            "cadence": "daily",
            "hour": self.hour,
            "minute": self.minute,
            "timeframe": "1_day",
        }

    def load_persisted_config(self) -> None:
        stored = google_sheets_service.load_setting("crawler_schedule")
        if stored:
            self._apply_config(stored)

    def _apply_config(self, config: dict[str, Any]) -> None:
        for name in ("enabled", "hour", "minute"):
            if name in config:
                setattr(self, name, config[name])
        self.timezone = "Asia/Ho_Chi_Minh"
        self.cadence = "daily"
        self.timeframe = "1_day"
        self.max_items = None

    def configure(self, config: dict[str, Any]) -> dict[str, Any]:
        was_running = self.is_running
        self._apply_config(config)
        if was_running:
            self.stop()
        self._calculate_next_run()
        google_sheets_service.save_setting("crawler_schedule", self._config_dict())
        if self.enabled:
            self.start(auto_bootstrap=False)
        return self.get_status()

    def start(self, auto_bootstrap: bool = True) -> None:
        if not self.enabled:
            logger.info("[Scheduler] Scheduler disabled by configuration.")
            return
        if self.is_running and self.current_task and not self.current_task.done():
            return
        self.is_running = True
        self._calculate_next_run()
        self.current_task = asyncio.create_task(self._main_scheduler_loop(auto_bootstrap))
        logger.info("[Scheduler] Started. Next run: %s", self.next_run_at)

    def stop(self) -> None:
        self.is_running = False
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        logger.info("[Scheduler] Stopped.")

    def _calculate_next_run(self) -> None:
        tz = ZoneInfo(self.timezone)
        now_local = datetime.datetime.now(tz)
        target_local = now_local.replace(
            hour=int(self.hour), minute=int(self.minute), second=0, microsecond=0
        )
        if target_local <= now_local:
            target_local += datetime.timedelta(days=1)
        self.next_run_at = target_local.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    async def _main_scheduler_loop(self, auto_bootstrap: bool = True) -> None:
        db = SessionLocal()
        try:
            lead_count = db.query(Lead).count()
        finally:
            db.close()
        self.bootstrap_done = lead_count > 0

        if auto_bootstrap and not self.bootstrap_done:
            try:
                self.last_run_summary["status"] = "BOOTSTRAPPING"
                await self._execute_run("1_month", 20, "BOOTSTRAP_SUCCESS")
                self.bootstrap_done = True
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("[Scheduler] Bootstrap failed: %s", exc, exc_info=True)
                self.last_run_summary["status"] = "BOOTSTRAP_FAILED"

        while self.is_running:
            try:
                self._calculate_next_run()
                sleep_seconds = max(1.0, (self.next_run_at - utc_now()).total_seconds())
                while sleep_seconds > 0 and self.is_running:
                    chunk = min(sleep_seconds, 60)
                    await asyncio.sleep(chunk)
                    sleep_seconds -= chunk
                if self.is_running and self.enabled:
                    await self._execute_run(self.timeframe, self.max_items)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[Scheduler] Scheduled run failed: %s", exc, exc_info=True)
                await asyncio.sleep(30)

    async def _execute_run(
        self,
        timeframe: str,
        max_items: Optional[int],
        success_status: str = "SUCCESS",
        manual: bool = False,
    ) -> Dict[str, Any]:
        self.last_run_summary["status"] = "RUNNING"
        runs = await crawler_service.run_all_sources(
            force_recrawl=False,
            max_items=max_items,
            timeframe=timeframe,
            is_manual_fe=manual,
        )
        self.last_run_at = utc_now()
        self.total_automated_runs += 1
        total_new = sum(run.new_leads for run in runs)
        total_discovered = sum(run.total_discovered for run in runs)
        total_errors = sum(run.error_count for run in runs)
        self.last_run_summary = {
            "status": success_status if total_errors == 0 else "PARTIAL",
            "new_leads": total_new,
            "total_discovered": total_discovered,
            "error_count": total_errors,
            "completed_at": self.last_run_at.isoformat(),
        }
        return self.last_run_summary

    async def trigger_immediate_run(self, timeframe: str = "1_month", max_items: Optional[int] = None) -> Dict[str, Any]:
        return await self._execute_run(timeframe, max_items, manual=True)

    def toggle(self, enabled: Optional[bool] = None) -> bool:
        new_enabled = (not self.enabled) if enabled is None else enabled
        self.configure({"enabled": new_enabled})
        return self.enabled

    def _schedule_label(self) -> str:
        return f"{int(self.hour):02d}:{int(self.minute):02d} hàng ngày"

    def get_status(self) -> Dict[str, Any]:
        next_local = None
        next_run_display = None
        if self.next_run_at:
            next_local_dt = self.next_run_at.replace(tzinfo=datetime.timezone.utc).astimezone(ZoneInfo(self.timezone))
            next_local = next_local_dt.isoformat()
            next_run_display = next_local_dt.strftime("%H:%M:%S %d/%m/%Y")
        return {
            "enabled": self.enabled,
            "is_running": self.is_running,
            "is_fe_task_active": priority_coordinator.is_fe_active,
            "bootstrap_completed": self.bootstrap_done,
            "schedule": self._config_dict(),
            "daily_schedule": f"{int(self.hour):02d}:{int(self.minute):02d} {self.timezone}",
            "schedule_label": self._schedule_label(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "next_run_local": next_local,
            "next_run_display": next_run_display,
            "total_automated_runs": self.total_automated_runs,
            "last_run_summary": self.last_run_summary,
        }


scheduler_service = SchedulerService()

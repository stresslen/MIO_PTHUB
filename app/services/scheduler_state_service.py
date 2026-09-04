from __future__ import annotations

import datetime
import json
import logging
from typing import Any
from zoneinfo import ZoneInfo

from app.config import settings
from app.database import SessionLocal
from app.models.source import CrawlJob, CrawlJobStatusEnum, SchedulerState
from app.pipeline.normalize import utc_now
from app.services.crawl_job_service import crawl_job_service

logger = logging.getLogger(__name__)
WORKER_FRESH_SECONDS = 20


class SchedulerStateService:
    """Small DB-backed control plane shared by API and crawl worker."""

    @staticmethod
    def _next_run(hour: int, minute: int, timezone: str, now: datetime.datetime | None = None) -> datetime.datetime:
        tz = ZoneInfo(timezone)
        current_utc = (now or utc_now()).replace(tzinfo=datetime.timezone.utc)
        current_local = current_utc.astimezone(tz)
        target_local = current_local.replace(
            hour=int(hour), minute=int(minute), second=0, microsecond=0
        )
        if target_local <= current_local:
            target_local += datetime.timedelta(days=1)
        return target_local.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    def _get_or_create(self, session) -> SchedulerState:
        state = session.get(SchedulerState, 1)
        if state is None:
            state = SchedulerState(
                id=1,
                enabled=settings.scheduler_enabled,
                timezone=settings.scheduler_timezone,
                hour=settings.scheduler_hour,
                minute=settings.scheduler_minute,
            )
            state.next_run_at = self._next_run(state.hour, state.minute, state.timezone)
            session.add(state)
            session.commit()
            session.refresh(state)
        elif state.next_run_at is None:
            state.next_run_at = self._next_run(state.hour, state.minute, state.timezone)
            session.commit()
        return state

    @staticmethod
    def _summary(state: SchedulerState) -> dict[str, Any]:
        if not state.last_run_summary_json:
            return {
                "status": "IDLE",
                "new_leads": 0,
                "total_discovered": 0,
                "error_count": 0,
            }
        try:
            value = json.loads(state.last_run_summary_json)
            return value if isinstance(value, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    def configure(self, config: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            state = self._get_or_create(session)
            state.enabled = bool(config.get("enabled", state.enabled))
            state.hour = int(config.get("hour", state.hour))
            state.minute = int(config.get("minute", state.minute))
            state.timezone = "Asia/Ho_Chi_Minh"
            state.next_run_at = self._next_run(state.hour, state.minute, state.timezone)
            state.config_updated_at = utc_now()
            state.config_dirty = True
            session.commit()
        finally:
            session.close()
        return self.get_status()

    def toggle(self, enabled: bool | None = None) -> bool:
        session = SessionLocal()
        try:
            state = self._get_or_create(session)
            state.enabled = (not state.enabled) if enabled is None else bool(enabled)
            state.next_run_at = self._next_run(state.hour, state.minute, state.timezone)
            state.config_updated_at = utc_now()
            state.config_dirty = True
            session.commit()
            return bool(state.enabled)
        finally:
            session.close()

    def get_status(self) -> dict[str, Any]:
        session = SessionLocal()
        try:
            state = self._get_or_create(session)
            heartbeat_age = None
            if state.worker_heartbeat_at:
                heartbeat_age = max(0.0, (utc_now() - state.worker_heartbeat_at).total_seconds())
            worker_online = heartbeat_age is not None and heartbeat_age <= WORKER_FRESH_SECONDS
            current_job = (
                session.query(CrawlJob)
                .filter(CrawlJob.status == CrawlJobStatusEnum.RUNNING.value)
                .order_by(CrawlJob.started_at.asc())
                .first()
            )
            next_local = None
            next_display = None
            if state.next_run_at:
                local_dt = state.next_run_at.replace(
                    tzinfo=datetime.timezone.utc
                ).astimezone(ZoneInfo(state.timezone))
                next_local = local_dt.isoformat()
                next_display = local_dt.strftime("%H:%M:%S %d/%m/%Y")
            return {
                "enabled": bool(state.enabled),
                "is_running": worker_online,
                "worker_online": worker_online,
                "worker_heartbeat_at": (
                    state.worker_heartbeat_at.isoformat() if state.worker_heartbeat_at else None
                ),
                "is_fe_task_active": False,
                "schedule": {
                    "enabled": bool(state.enabled),
                    "timezone": state.timezone,
                    "cadence": "daily",
                    "hour": state.hour,
                    "minute": state.minute,
                    "timeframe": "1_day",
                },
                "daily_schedule": f"{state.hour:02d}:{state.minute:02d} {state.timezone}",
                "schedule_label": f"{state.hour:02d}:{state.minute:02d} hàng ngày",
                "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
                "next_run_at": state.next_run_at.isoformat() if state.next_run_at else None,
                "next_run_local": next_local,
                "next_run_display": next_display,
                "total_automated_runs": state.total_automated_runs,
                "last_run_summary": self._summary(state),
                "queue_depth": crawl_job_service.queue_depth(),
                "current_job_id": current_job.id if current_job else None,
            }
        finally:
            session.close()

    def heartbeat(self) -> None:
        session = SessionLocal()
        try:
            state = self._get_or_create(session)
            state.worker_heartbeat_at = utc_now()
            session.commit()
        finally:
            session.close()

    def enqueue_due_job(self) -> str | None:
        session = SessionLocal()
        try:
            state = self._get_or_create(session)
            now = utc_now()
            if not state.enabled or not state.next_run_at or state.next_run_at > now:
                return None
            scheduled_for = state.next_run_at
            dedupe_key = "scheduled:" + scheduled_for.strftime("%Y-%m-%dT%H:%M")
            job = crawl_job_service.enqueue(
                source_id=None,
                timeframe="1_day",
                force_recrawl=False,
                trigger="SCHEDULE",
                dedupe_key=dedupe_key,
                db=session,
            )
            state.next_run_at = self._next_run(
                state.hour,
                state.minute,
                state.timezone,
                now=now + datetime.timedelta(seconds=1),
            )
            session.commit()
            return job.id
        finally:
            session.close()

    def record_scheduled_result(self, result: dict[str, Any]) -> None:
        session = SessionLocal()
        try:
            state = self._get_or_create(session)
            state.last_run_at = utc_now()
            state.total_automated_runs += 1
            state.last_run_summary_json = json.dumps(result, ensure_ascii=False)
            session.commit()
        finally:
            session.close()

    def load_persistent_config_for_worker(self) -> None:
        """Ensure the persistent SQLite scheduler config is marked loaded."""
        session = SessionLocal()
        try:
            state = self._get_or_create(session)
            state.persistent_config_loaded = True
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("[Scheduler] Lỗi nạp cấu hình scheduler từ SQLite")
        finally:
            session.close()

    def sync_dirty_config_to_sheets(self) -> None:
        """Mark dirty config as clean in SQLite (Google Sheets sync is disabled)."""
        session = SessionLocal()
        try:
            state = self._get_or_create(session)
            if state.config_dirty:
                state.config_dirty = False
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()


scheduler_state_service = SchedulerStateService()

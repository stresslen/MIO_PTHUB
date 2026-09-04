from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Iterable

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.source import (
    CrawlJob,
    CrawlJobRead,
    CrawlJobStatusEnum,
    CrawlRun,
    CrawlStatusEnum,
)
from app.pipeline.normalize import utc_now

logger = logging.getLogger(__name__)


class CrawlJobService:
    """Database-backed queue shared by the lightweight API and crawl worker."""

    @staticmethod
    def _read(job: CrawlJob) -> CrawlJobRead:
        result = None
        if job.result_json:
            try:
                parsed = json.loads(job.result_json)
                result = parsed if isinstance(parsed, dict) else None
            except (TypeError, json.JSONDecodeError):
                result = None
        return CrawlJobRead(
            id=job.id,
            source_id=job.source_id,
            trigger=job.trigger,
            status=job.status,
            timeframe=job.timeframe,
            force_recrawl=bool(job.force_recrawl),
            requested_at=job.requested_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=result,
            error_message=job.error_message,
        )

    def enqueue(
        self,
        *,
        source_id: str | None,
        timeframe: str,
        force_recrawl: bool = False,
        trigger: str = "FE",
        dedupe_key: str | None = None,
        db: Session | None = None,
    ) -> CrawlJobRead:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            if dedupe_key:
                existing = session.query(CrawlJob).filter(CrawlJob.dedupe_key == dedupe_key).first()
                if existing is not None:
                    return self._read(existing)
            job = CrawlJob(
                source_id=source_id,
                timeframe=timeframe,
                force_recrawl=force_recrawl,
                trigger=trigger.upper(),
                status=CrawlJobStatusEnum.QUEUED.value,
                requested_at=utc_now(),
                dedupe_key=dedupe_key,
            )
            session.add(job)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                if not dedupe_key:
                    raise
                existing = session.query(CrawlJob).filter(CrawlJob.dedupe_key == dedupe_key).one()
                return self._read(existing)
            session.refresh(job)
            logger.info(
                "[CrawlQueue] Enqueued job %s (source=%s, trigger=%s)",
                job.id,
                source_id or "all",
                job.trigger,
            )
            return self._read(job)
        finally:
            if owns_session:
                session.close()

    def get(self, job_id: str, db: Session | None = None) -> CrawlJobRead | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            job = session.get(CrawlJob, job_id)
            return self._read(job) if job is not None else None
        finally:
            if owns_session:
                session.close()

    def recent(self, limit: int = 20, db: Session | None = None) -> list[CrawlJobRead]:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            jobs = (
                session.query(CrawlJob)
                .order_by(CrawlJob.requested_at.desc())
                .limit(max(1, min(limit, 100)))
                .all()
            )
            return [self._read(job) for job in jobs]
        finally:
            if owns_session:
                session.close()

    def claim_next(self, worker_id: str) -> CrawlJobRead | None:
        """Atomically claim one FIFO job; safe if a second worker is started by mistake."""
        session = SessionLocal()
        try:
            candidate_ids: Iterable[str] = (
                row[0]
                for row in session.query(CrawlJob.id)
                .filter(CrawlJob.status == CrawlJobStatusEnum.QUEUED.value)
                .order_by(CrawlJob.requested_at.asc())
                .limit(10)
                .all()
            )
            for job_id in candidate_ids:
                claimed = session.execute(
                    update(CrawlJob)
                    .where(
                        CrawlJob.id == job_id,
                        CrawlJob.status == CrawlJobStatusEnum.QUEUED.value,
                    )
                    .values(
                        status=CrawlJobStatusEnum.RUNNING.value,
                        started_at=utc_now(),
                        completed_at=None,
                        worker_id=worker_id,
                        error_message=None,
                    )
                )
                if claimed.rowcount != 1:
                    session.rollback()
                    continue
                session.commit()
                job = session.get(CrawlJob, job_id)
                return self._read(job) if job is not None else None
            return None
        finally:
            session.close()

    def finish(
        self,
        job_id: str,
        *,
        status: CrawlJobStatusEnum | str,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> CrawlJobRead:
        session = SessionLocal()
        try:
            job = session.get(CrawlJob, job_id)
            if job is None:
                raise KeyError(job_id)
            job.status = status.value if isinstance(status, CrawlJobStatusEnum) else str(status)
            job.completed_at = utc_now()
            job.result_json = json.dumps(result or {}, ensure_ascii=False)
            job.error_message = error_message
            session.commit()
            session.refresh(job)
            return self._read(job)
        finally:
            session.close()

    def recover_interrupted_jobs(self) -> int:
        """Put unfinished jobs back in FIFO order after a worker restart."""
        session = SessionLocal()
        try:
            jobs = (
                session.query(CrawlJob)
                .filter(CrawlJob.status == CrawlJobStatusEnum.RUNNING.value)
                .all()
            )
            for job in jobs:
                job.status = CrawlJobStatusEnum.QUEUED.value
                job.started_at = None
                job.worker_id = None
                job.error_message = "Worker trước đã dừng; job được đưa lại vào hàng đợi"
            if jobs:
                session.commit()
            return len(jobs)
        finally:
            session.close()

    def get_job_status(self, job_id: str, db: Session | None = None) -> str | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            row = session.query(CrawlJob.status).filter(CrawlJob.id == job_id).first()
            return row[0] if row else None
        finally:
            if owns_session:
                session.close()

    def stop_job(
        self,
        job_id: str,
        reason: str = "Đã dừng bởi người dùng",
        db: Session | None = None,
    ) -> CrawlJobRead | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            job = session.get(CrawlJob, job_id)
            if job is None:
                return None

            was_running = job.status == CrawlJobStatusEnum.RUNNING.value
            job.status = CrawlJobStatusEnum.INTERRUPTED.value
            job.completed_at = utc_now()
            job.error_message = reason

            if was_running:
                running_runs = (
                    session.query(CrawlRun)
                    .filter(CrawlRun.status == CrawlStatusEnum.RUNNING.value)
                    .all()
                )
                for run in running_runs:
                    run.status = CrawlStatusEnum.INTERRUPTED.value
                    run.end_time = utc_now()
                    run.error_message = reason

            session.commit()
            session.refresh(job)
            logger.info("[CrawlQueue] Stopped job %s (was_running=%s)", job_id, was_running)
            return self._read(job)
        finally:
            if owns_session:
                session.close()

    def stop_active(
        self,
        reason: str = "Đã dừng bởi người dùng",
        db: Session | None = None,
    ) -> CrawlJobRead | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            running = (
                session.query(CrawlJob)
                .filter(CrawlJob.status == CrawlJobStatusEnum.RUNNING.value)
                .first()
            )
            if running:
                return self.stop_job(running.id, reason=reason, db=session)

            # Check if any CrawlRun is running directly (CLI/direct run)
            running_runs = (
                session.query(CrawlRun)
                .filter(CrawlRun.status == CrawlStatusEnum.RUNNING.value)
                .all()
            )
            if running_runs:
                now = utc_now()
                for run in running_runs:
                    run.status = CrawlStatusEnum.INTERRUPTED.value
                    run.end_time = now
                    run.error_message = reason
                session.commit()
                return CrawlJobRead(
                    id=running_runs[0].id,
                    source_id=running_runs[0].source,
                    trigger="CLI",
                    status=CrawlJobStatusEnum.INTERRUPTED,
                    timeframe="1_week",
                    force_recrawl=False,
                    requested_at=running_runs[0].start_time or now,
                    started_at=running_runs[0].start_time or now,
                    completed_at=now,
                    error_message=reason,
                )

            next_queued = (
                session.query(CrawlJob)
                .filter(CrawlJob.status == CrawlJobStatusEnum.QUEUED.value)
                .order_by(CrawlJob.requested_at.asc())
                .first()
            )
            if next_queued:
                return self.stop_job(next_queued.id, reason=reason, db=session)

            return None
        finally:
            if owns_session:
                session.close()

    def pause_active(
        self,
        reason: str = "Tạm dừng bởi người dùng",
        db: Session | None = None,
    ) -> CrawlJobRead | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            running = (
                session.query(CrawlJob)
                .filter(CrawlJob.status == CrawlJobStatusEnum.RUNNING.value)
                .first()
            )
            if running:
                running.status = CrawlJobStatusEnum.PAUSED.value
                running.error_message = reason
                session.commit()
                session.refresh(running)
                logger.info("[CrawlQueue] Paused active running job %s", running.id)
                return self._read(running)
            return None
        finally:
            if owns_session:
                session.close()

    def resume_active(
        self,
        db: Session | None = None,
    ) -> CrawlJobRead | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            paused = (
                session.query(CrawlJob)
                .filter(CrawlJob.status == CrawlJobStatusEnum.PAUSED.value)
                .order_by(CrawlJob.requested_at.asc())
                .first()
            )
            if paused:
                if paused.started_at:
                    paused.status = CrawlJobStatusEnum.RUNNING.value
                else:
                    paused.status = CrawlJobStatusEnum.QUEUED.value
                paused.error_message = None
                session.commit()
                session.refresh(paused)
                logger.info("[CrawlQueue] Resumed active paused job %s to %s", paused.id, paused.status)
                return self._read(paused)
            return None
        finally:
            if owns_session:
                session.close()

    def pause_job(self, job_id: str, db: Session | None = None) -> CrawlJobRead | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            job = session.get(CrawlJob, job_id)
            if job is None:
                return None
            if job.status in (CrawlJobStatusEnum.QUEUED.value, CrawlJobStatusEnum.RUNNING.value):
                job.status = CrawlJobStatusEnum.PAUSED.value
                job.error_message = "Tạm dừng bởi người dùng"
                session.commit()
                session.refresh(job)
                logger.info("[CrawlQueue] Paused job %s", job_id)
            return self._read(job)
        finally:
            if owns_session:
                session.close()

    def resume_job(self, job_id: str, db: Session | None = None) -> CrawlJobRead | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            job = session.get(CrawlJob, job_id)
            if job is None:
                return None
            if job.status == CrawlJobStatusEnum.PAUSED.value:
                if job.started_at:
                    job.status = CrawlJobStatusEnum.RUNNING.value
                else:
                    job.status = CrawlJobStatusEnum.QUEUED.value
                job.error_message = None
                session.commit()
                session.refresh(job)
                logger.info("[CrawlQueue] Resumed job %s to %s", job_id, job.status)
            elif job.status in (
                CrawlJobStatusEnum.INTERRUPTED.value,
                CrawlJobStatusEnum.FAILED.value,
            ):
                job.status = CrawlJobStatusEnum.QUEUED.value
                job.worker_id = None
                job.started_at = None
                job.completed_at = None
                job.error_message = None
                session.commit()
                session.refresh(job)
                logger.info("[CrawlQueue] Resumed job %s to QUEUED", job_id)
            return self._read(job)
        finally:
            if owns_session:
                session.close()

    def promote_job(self, job_id: str, db: Session | None = None) -> CrawlJobRead | None:
        """Move job to the very front of the queue."""
        owns_session = db is None
        session = db or SessionLocal()
        try:
            job = session.get(CrawlJob, job_id)
            if job is None:
                return None
            earliest = (
                session.query(CrawlJob.requested_at)
                .filter(CrawlJob.status == CrawlJobStatusEnum.QUEUED.value)
                .order_by(CrawlJob.requested_at.asc())
                .first()
            )
            now = utc_now()
            if earliest and earliest[0]:
                job.requested_at = earliest[0] - datetime.timedelta(seconds=10)
            else:
                job.requested_at = now
            job.status = CrawlJobStatusEnum.QUEUED.value
            job.started_at = None
            job.completed_at = None
            job.error_message = None
            session.commit()
            session.refresh(job)
            logger.info("[CrawlQueue] Promoted job %s to front of queue", job_id)
            return self._read(job)
        finally:
            if owns_session:
                session.close()

    def delete_job(self, job_id: str, db: Session | None = None) -> bool:
        """Permanently delete a crawl job. If currently running or paused, stop it first."""
        owns_session = db is None
        session = db or SessionLocal()
        try:
            job = session.get(CrawlJob, job_id)
            if job is None:
                return False
            if job.status in (CrawlJobStatusEnum.RUNNING.value, CrawlJobStatusEnum.PAUSED.value):
                self.stop_job(job_id, reason="Đã xóa bởi người dùng", db=session)
            session.delete(job)
            session.commit()
            logger.info("[CrawlQueue] Deleted job %s", job_id)
            return True
        finally:
            if owns_session:
                session.close()

    def delete_active(self, db: Session | None = None) -> bool:
        """Stop and delete the running or paused job, or delete the next queued job."""
        owns_session = db is None
        session = db or SessionLocal()
        try:
            active = (
                session.query(CrawlJob)
                .filter(
                    CrawlJob.status.in_([
                        CrawlJobStatusEnum.RUNNING.value,
                        CrawlJobStatusEnum.PAUSED.value,
                    ])
                )
                .first()
            )
            if active:
                return self.delete_job(active.id, db=session)

            # Check if any CrawlRun is running directly (CLI/direct run)
            running_runs = (
                session.query(CrawlRun)
                .filter(CrawlRun.status == CrawlStatusEnum.RUNNING.value)
                .all()
            )
            if running_runs:
                now = utc_now()
                for run in running_runs:
                    run.status = CrawlStatusEnum.INTERRUPTED.value
                    run.end_time = now
                    run.error_message = "Đã xóa bởi người dùng"
                session.commit()
                return True

            next_queued = (
                session.query(CrawlJob)
                .filter(
                    CrawlJob.status.in_([
                        CrawlJobStatusEnum.QUEUED.value,
                        CrawlJobStatusEnum.PAUSED.value,
                    ])
                )
                .order_by(CrawlJob.requested_at.asc())
                .first()
            )
            if next_queued:
                return self.delete_job(next_queued.id, db=session)

            return False
        finally:
            if owns_session:
                session.close()

    def pause_all_queued(self, db: Session | None = None) -> int:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            count = (
                session.query(CrawlJob)
                .filter(CrawlJob.status == CrawlJobStatusEnum.QUEUED.value)
                .update({CrawlJob.status: CrawlJobStatusEnum.PAUSED.value})
            )
            session.commit()
            logger.info("[CrawlQueue] Paused all queued jobs (count=%s)", count)
            return count
        finally:
            if owns_session:
                session.close()

    def resume_all_paused(self, db: Session | None = None) -> int:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            count = (
                session.query(CrawlJob)
                .filter(CrawlJob.status == CrawlJobStatusEnum.PAUSED.value)
                .update({CrawlJob.status: CrawlJobStatusEnum.QUEUED.value})
            )
            session.commit()
            logger.info("[CrawlQueue] Resumed all paused jobs (count=%s)", count)
            return count
        finally:
            if owns_session:
                session.close()

    def queue_depth(self) -> int:
        session = SessionLocal()
        try:
            return (
                session.query(CrawlJob)
                .filter(
                    CrawlJob.status.in_([
                        CrawlJobStatusEnum.QUEUED.value,
                        CrawlJobStatusEnum.PAUSED.value,
                    ])
                )
                .count()
            )
        finally:
            session.close()


crawl_job_service = CrawlJobService()

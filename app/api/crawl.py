from __future__ import annotations

import datetime
import json
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.source import (
    CrawlJob,
    CrawlJobRead,
    CrawlJobStatusEnum,
    CrawlRun,
    CrawlStatusEnum,
    TriggerCrawlRequest,
)
from app.pipeline.normalize import utc_now
from app.services.crawl_job_service import crawl_job_service
from app.services.source_service import source_service


router = APIRouter(prefix="/crawl", tags=["Crawl"])

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def to_vn_iso(dt: datetime.datetime | None) -> str | None:
    """Convert a UTC or naive datetime into a Vietnam (GMT+7) ISO string."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(VN_TZ).isoformat()


TIMEFRAME_LABELS: dict[str, str] = {
    "1_day": "24 giờ qua",
    "1_week": "7 ngày qua",
    "1_month": "30 ngày qua",
}

TRIGGER_LABELS: dict[str, str] = {
    "FE": "Thủ công từ giao diện",
    "SCHEDULE": "Tự động theo lịch",
    "CLI": "Dòng lệnh",
}


def _format_job_payload(job: Any) -> dict[str, Any]:
    if job is None:
        return {}
    if isinstance(job, CrawlJob):
        result = None
        if job.result_json:
            try:
                parsed = json.loads(job.result_json)
                result = parsed if isinstance(parsed, dict) else None
            except Exception:
                result = None
        data = {
            "id": job.id,
            "source_id": job.source_id,
            "trigger": job.trigger or "FE",
            "status": str(getattr(job.status, "value", job.status)) if job.status else "RUNNING",
            "timeframe": job.timeframe or "1_week",
            "force_recrawl": bool(job.force_recrawl),
            "requested_at": to_vn_iso(job.requested_at),
            "started_at": to_vn_iso(job.started_at),
            "completed_at": to_vn_iso(job.completed_at),
            "result": result,
            "error_message": job.error_message,
        }
        return data
    if hasattr(job, "model_dump"):
        data = job.model_dump()
    elif hasattr(job, "dict"):
        data = job.dict()
    elif isinstance(job, dict):
        data = dict(job)
    else:
        data = {}

    if "status" in data and hasattr(data["status"], "value"):
        data["status"] = data["status"].value
    elif "status" in data and data["status"] is not None:
        data["status"] = str(data["status"])

    req_at = getattr(job, "requested_at", None)
    if req_at:
        data["requested_at"] = to_vn_iso(req_at)
    start_at = getattr(job, "started_at", None)
    if start_at:
        data["started_at"] = to_vn_iso(start_at)
    comp_at = getattr(job, "completed_at", None)
    if comp_at:
        data["completed_at"] = to_vn_iso(comp_at)
    return data


def _get_queued_jobs_list(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    queued_records = (
        db.query(CrawlJob)
        .filter(
            CrawlJob.status.in_([
                CrawlJobStatusEnum.QUEUED.value,
                CrawlJobStatusEnum.PAUSED.value,
            ])
        )
        .order_by(CrawlJob.requested_at.asc())
        .limit(limit)
        .all()
    )
    queued_list = []
    for idx, q in enumerate(queued_records, start=1):
        s_item = source_service.get(q.source_id) if q.source_id else None
        src_name = s_item.get("name", q.source_id) if s_item else "Tất cả các nguồn dữ liệu"
        queued_list.append({
            "id": q.id,
            "order": idx,
            "status": q.status,
            "source_id": q.source_id,
            "source_name": src_name,
            "timeframe": q.timeframe,
            "timeframe_label": TIMEFRAME_LABELS.get(q.timeframe, q.timeframe),
            "trigger_label": TRIGGER_LABELS.get(q.trigger, q.trigger),
            "requested_at": to_vn_iso(q.requested_at),
        })
    return queued_list


@router.post(
    "/run",
    response_model=CrawlJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_crawl(
    request: TriggerCrawlRequest,
    sync: bool = Query(
        False,
        description="Deprecated. Crawl is always queued for the dedicated worker.",
    ),
    db: Session = Depends(get_db),
):
    """Queue crawl work and return immediately; never execute browser/AI work in FastAPI."""
    del sync
    if request.source_id and source_service.get(request.source_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nguồn crawl")
    return crawl_job_service.enqueue(
        source_id=request.source_id,
        timeframe=request.timeframe,
        force_recrawl=request.force_recrawl,
        trigger="FE",
        db=db,
    )


@router.get("/active")
def get_active_crawl_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return structured real-time status of running or queued crawl job, or active background run."""
    queue_depth = crawl_job_service.queue_depth()
    queued_jobs = _get_queued_jobs_list(db)

    # 1. Check for active CrawlJob (either RUNNING or PAUSED)
    running_job = (
        db.query(CrawlJob)
        .filter(
            CrawlJob.status.in_([
                CrawlJobStatusEnum.RUNNING.value,
                CrawlJobStatusEnum.PAUSED.value,
            ])
        )
        .order_by(CrawlJob.started_at.desc())
        .first()
    )

    if running_job:
        s_item = source_service.get(running_job.source_id) if running_job.source_id else None
        src_name = s_item.get("name", running_job.source_id) if s_item else "Tất cả các nguồn dữ liệu"

        active_runs = (
            db.query(CrawlRun)
            .filter(
                CrawlRun.status.in_([
                    CrawlStatusEnum.RUNNING.value,
                ])
            )
            .all()
        )
        active_runs_info = [
            {
                "source_id": r.source,
                "source_name": (source_service.get(r.source) or {}).get("name", r.source),
                "total_discovered": r.total_discovered or 0,
                "new_leads": r.new_leads or 0,
            }
            for r in active_runs
        ]

        job_data = _format_job_payload(running_job)
        job_data["source_name"] = src_name
        job_data["timeframe_label"] = TIMEFRAME_LABELS.get(running_job.timeframe, running_job.timeframe)
        job_data["trigger_label"] = TRIGGER_LABELS.get(running_job.trigger, running_job.trigger)
        job_data["active_runs"] = active_runs_info
        job_data["is_paused"] = (running_job.status == CrawlJobStatusEnum.PAUSED.value)

        if running_job.started_at:
            job_data["elapsed_seconds"] = max(0, int((utc_now() - running_job.started_at).total_seconds()))
        else:
            job_data["elapsed_seconds"] = 0

        return {
            "has_active": True,
            "queue_depth": queue_depth,
            "active_job": job_data,
            "recent_job": None,
            "queued_jobs": queued_jobs,
        }

    # 2. Check for active CrawlRun directly (e.g. from terminal CLI, direct script, or scheduler)
    active_crawl_run = (
        db.query(CrawlRun)
        .filter(CrawlRun.status == CrawlStatusEnum.RUNNING.value)
        .order_by(CrawlRun.start_time.desc())
        .first()
    )

    if active_crawl_run:
        all_running_runs = (
            db.query(CrawlRun)
            .filter(CrawlRun.status == CrawlStatusEnum.RUNNING.value)
            .all()
        )
        active_runs_info = [
            {
                "source_id": r.source,
                "source_name": (source_service.get(r.source) or {}).get("name", r.source),
                "total_discovered": r.total_discovered or 0,
                "new_leads": r.new_leads or 0,
            }
            for r in all_running_runs
        ]

        s_item = source_service.get(active_crawl_run.source) if active_crawl_run.source else None
        src_name = s_item.get("name", active_crawl_run.source) if s_item else active_crawl_run.source
        if len(all_running_runs) > 1:
            src_name = f"Tất cả các nguồn ({len(all_running_runs)} nguồn đang chạy)"

        now = utc_now()
        elapsed = int((now - active_crawl_run.start_time).total_seconds()) if active_crawl_run.start_time else 0

        job_data = {
            "id": active_crawl_run.id,
            "source_id": active_crawl_run.source,
            "source_name": src_name,
            "status": "RUNNING",
            "trigger": "CLI",
            "trigger_label": "Tiến trình đang chạy",
            "timeframe": "1_week",
            "timeframe_label": "7 ngày qua",
            "elapsed_seconds": max(0, elapsed),
            "started_at": to_vn_iso(active_crawl_run.start_time),
            "requested_at": to_vn_iso(active_crawl_run.start_time),
            "active_runs": active_runs_info,
        }

        return {
            "has_active": True,
            "queue_depth": queue_depth,
            "active_job": job_data,
            "recent_job": None,
            "queued_jobs": queued_jobs,
        }

    # 3. Check for next QUEUED CrawlJob
    queued_job = (
        db.query(CrawlJob)
        .filter(CrawlJob.status == CrawlJobStatusEnum.QUEUED.value)
        .order_by(CrawlJob.requested_at.asc())
        .first()
    )

    if queued_job:
        s_item = source_service.get(queued_job.source_id) if queued_job.source_id else None
        src_name = s_item.get("name", queued_job.source_id) if s_item else "Tất cả các nguồn dữ liệu"

        job_data = _format_job_payload(queued_job)
        job_data["source_name"] = src_name
        job_data["timeframe_label"] = TIMEFRAME_LABELS.get(queued_job.timeframe, queued_job.timeframe)
        job_data["trigger_label"] = TRIGGER_LABELS.get(queued_job.trigger, queued_job.trigger)
        job_data["active_runs"] = []
        job_data["elapsed_seconds"] = 0

        return {
            "has_active": True,
            "queue_depth": queue_depth,
            "active_job": job_data,
            "recent_job": None,
            "queued_jobs": queued_jobs,
        }

    # 4. Check for recent completed / interrupted job
    recent_job = (
        db.query(CrawlJob)
        .filter(
            CrawlJob.status.in_([
                CrawlJobStatusEnum.SUCCESS.value,
                CrawlJobStatusEnum.PARTIAL.value,
                CrawlJobStatusEnum.FAILED.value,
                CrawlJobStatusEnum.INTERRUPTED.value,
            ])
        )
        .order_by(CrawlJob.completed_at.desc())
        .first()
    )
    recent_dict = None
    if recent_job and recent_job.completed_at:
        age_sec = (utc_now() - recent_job.completed_at).total_seconds()
        if age_sec < 600:
            s_item = source_service.get(recent_job.source_id) if recent_job.source_id else None
            src_name = s_item.get("name", recent_job.source_id) if s_item else "Tất cả các nguồn"
            recent_dict = _format_job_payload(recent_job)
            recent_dict["source_name"] = src_name
            recent_dict["timeframe_label"] = TIMEFRAME_LABELS.get(recent_job.timeframe, recent_job.timeframe)
            recent_dict["trigger_label"] = TRIGGER_LABELS.get(recent_job.trigger, recent_job.trigger)
            recent_dict["completed_seconds_ago"] = int(age_sec)

    return {
        "has_active": False,
        "queue_depth": queue_depth,
        "active_job": None,
        "recent_job": recent_dict,
        "queued_jobs": queued_jobs,
    }


@router.post("/active/pause")
def pause_active_crawl(db: Session = Depends(get_db)):
    """Pause the running crawl job without cancelling or deleting it."""
    paused = crawl_job_service.pause_active(reason="Tạm dừng bởi người dùng", db=db)
    if not paused:
        return {"status": "noop", "message": "Không có luồng crawl nào đang chạy để tạm dừng"}
    return {"status": "ok", "message": "Đã tạm dừng luồng crawl", "job": _format_job_payload(paused)}


@router.post("/active/resume")
def resume_active_crawl(db: Session = Depends(get_db)):
    """Resume the paused crawl job."""
    resumed = crawl_job_service.resume_active(db=db)
    if not resumed:
        return {"status": "noop", "message": "Không có luồng crawl nào đang tạm dừng để tiếp tục"}
    return {"status": "ok", "message": "Đã tiếp tục luồng crawl", "job": _format_job_payload(resumed)}


@router.post("/active/stop")
def stop_active_crawl(db: Session = Depends(get_db)):
    """Pause/stop the active crawl job."""
    paused = crawl_job_service.pause_active(reason="Tạm dừng bởi người dùng", db=db)
    if paused:
        return {"status": "ok", "message": "Đã tạm dừng luồng crawl", "job": _format_job_payload(paused)}
    stopped = crawl_job_service.stop_active(reason="Đã dừng bởi người dùng", db=db)
    if not stopped:
        return {"status": "noop", "message": "Không có luồng crawl nào đang chạy hoặc chờ"}
    return {"status": "ok", "job": _format_job_payload(stopped)}


@router.delete("/active")
def delete_active_crawl(db: Session = Depends(get_db)):
    """Stop and delete the running, paused or next queued crawl job."""
    deleted = crawl_job_service.delete_active(db=db)
    if not deleted:
        return {"status": "noop", "message": "Không có luồng crawl nào đang chạy, tạm dừng hoặc chờ để xóa"}
    return {"status": "ok", "message": "Đã xóa luồng crawl thành công"}


@router.post("/jobs/{job_id}/stop")
def stop_crawl_job(job_id: str, db: Session = Depends(get_db)):
    """Stop a running or queued job."""
    stopped = crawl_job_service.stop_job(job_id, reason="Đã dừng bởi người dùng", db=db)
    if not stopped:
        raise HTTPException(status_code=404, detail="Không tìm thấy crawl job")
    return {"status": "ok", "job": _format_job_payload(stopped)}


@router.post("/jobs/{job_id}/pause")
def pause_crawl_job(job_id: str, db: Session = Depends(get_db)):
    """Pause a queued crawl job."""
    job = crawl_job_service.pause_job(job_id, db=db)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy crawl job")
    return {"status": "ok", "job": _format_job_payload(job)}


@router.post("/jobs/{job_id}/resume")
def resume_crawl_job(job_id: str, db: Session = Depends(get_db)):
    """Resume a paused, interrupted, or failed crawl job."""
    job = crawl_job_service.resume_job(job_id, db=db)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy crawl job")
    return {"status": "ok", "job": _format_job_payload(job)}


@router.post("/jobs/{job_id}/promote")
def promote_crawl_job(job_id: str, db: Session = Depends(get_db)):
    """Move a queued or paused crawl job to the front of the queue."""
    job = crawl_job_service.promote_job(job_id, db=db)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy crawl job")
    return {"status": "ok", "job": _format_job_payload(job)}


@router.delete("/jobs/{job_id}")
def delete_crawl_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a specific crawl job."""
    deleted = crawl_job_service.delete_job(job_id, db=db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy crawl job")
    return {"status": "ok", "deleted_id": job_id}


@router.post("/queue/pause-all")
def pause_all_queued_jobs(db: Session = Depends(get_db)):
    """Pause all queued jobs."""
    count = crawl_job_service.pause_all_queued(db=db)
    return {"status": "ok", "paused_count": count}


@router.post("/queue/resume-all")
def resume_all_paused_jobs(db: Session = Depends(get_db)):
    """Resume all paused jobs."""
    count = crawl_job_service.resume_all_paused(db=db)
    return {"status": "ok", "resumed_count": count}


@router.delete("/queue")
def clear_crawl_queue(db: Session = Depends(get_db)):
    """Delete all queued or paused crawl jobs."""
    deleted = (
        db.query(CrawlJob)
        .filter(
            CrawlJob.status.in_([
                CrawlJobStatusEnum.QUEUED.value,
                CrawlJobStatusEnum.PAUSED.value,
            ])
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"status": "ok", "deleted_count": deleted}


@router.get("/jobs", response_model=list[CrawlJobRead])
def list_crawl_jobs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return crawl_job_service.recent(limit=limit, db=db)


@router.get("/jobs/{job_id}", response_model=CrawlJobRead)
def get_crawl_job(job_id: str, db: Session = Depends(get_db)):
    job = crawl_job_service.get(job_id, db=db)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy crawl job")
    return job


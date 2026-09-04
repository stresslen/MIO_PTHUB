from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from app.database import Base, SessionLocal, init_db
from app.main import app
from app.models.source import CrawlJob, CrawlJobStatusEnum
import app.services.crawl_job_service as crawl_job_module
from app.services.crawl_job_service import crawl_job_service
from scripts.crawl_worker import CrawlWorker


def _delete_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(CrawlJob).filter(CrawlJob.id == job_id).delete()
        db.commit()
    finally:
        db.close()


def test_api_always_queues_crawl_even_when_legacy_sync_is_true():
    init_db()
    response = TestClient(app).post(
        "/api/crawl/run?sync=true",
        json={
            "source_id": "baodauthau",
            "timeframe": "1_day",
            "force_recrawl": False,
        },
    )
    assert response.status_code == 202
    job = response.json()
    try:
        assert job["status"] == "QUEUED"
        assert job["source_id"] == "baodauthau"
        stored = TestClient(app).get(f"/api/crawl/jobs/{job['id']}")
        assert stored.status_code == 200
        assert stored.json()["status"] == "QUEUED"
    finally:
        _delete_job(job["id"])


def test_queue_claim_and_finish_round_trip(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'crawl-queue.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    temp_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(crawl_job_module, "SessionLocal", temp_session)

    queued = crawl_job_service.enqueue(
        source_id="baodauthau",
        timeframe="1_week",
        trigger="TEST",
    )
    claimed = crawl_job_service.claim_next("pytest-worker")
    assert claimed is not None
    assert claimed.id == queued.id
    assert claimed.status == CrawlJobStatusEnum.RUNNING

    finished = crawl_job_service.finish(
        queued.id,
        status=CrawlJobStatusEnum.SUCCESS,
        result={"new_leads": 3, "total_discovered": 7},
    )
    assert finished.status == CrawlJobStatusEnum.SUCCESS
    assert finished.result == {"new_leads": 3, "total_discovered": 7}


def test_worker_summary_maps_partial_runs_and_totals():
    runs = [
        SimpleNamespace(
            id="run-1",
            source="source-a",
            status="SUCCESS",
            total_discovered=5,
            new_leads=2,
            duplicate_leads=1,
            filtered_out=2,
            error_count=0,
            error_message=None,
        ),
        SimpleNamespace(
            id="run-2",
            source="source-b",
            status="PARTIAL",
            total_discovered=4,
            new_leads=1,
            duplicate_leads=0,
            filtered_out=1,
            error_count=2,
            error_message="Hai trang lỗi",
        ),
    ]

    status, summary = CrawlWorker._summarize(runs)

    assert status == CrawlJobStatusEnum.PARTIAL
    assert summary["total_discovered"] == 9
    assert summary["new_leads"] == 3
    assert summary["error_count"] == 2


def test_get_active_crawl_status():
    init_db()
    client = TestClient(app)
    response = client.get("/api/crawl/active")
    assert response.status_code == 200
    data = response.json()
    assert "has_active" in data
    assert "queue_depth" in data
    if data["has_active"]:
        assert "active_job" in data
        assert "source_name" in data["active_job"]
        assert "timeframe_label" in data["active_job"]
        assert "trigger_label" in data["active_job"]
        assert "elapsed_seconds" in data["active_job"]


def test_pause_and_resume_active_job(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test-pause-resume.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    temp_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(crawl_job_module, "SessionLocal", temp_session)

    # 1. Enqueue and Claim job to make it RUNNING
    job = crawl_job_service.enqueue(source_id="baodauthau", timeframe="1_day", trigger="TEST")
    claimed = crawl_job_service.claim_next("worker-test")
    assert claimed is not None
    assert claimed.status == CrawlJobStatusEnum.RUNNING

    # 2. Pause active job
    paused = crawl_job_service.pause_active(reason="Tạm dừng test")
    assert paused is not None
    assert paused.status == CrawlJobStatusEnum.PAUSED

    # Status check confirms it remains PAUSED and not deleted
    status = crawl_job_service.get_job_status(job.id)
    assert status == CrawlJobStatusEnum.PAUSED.value

    # 3. Resume active job
    resumed = crawl_job_service.resume_active()
    assert resumed is not None
    assert resumed.status == CrawlJobStatusEnum.RUNNING

    status = crawl_job_service.get_job_status(job.id)
    assert status == CrawlJobStatusEnum.RUNNING.value


def test_delete_active_job_allows_next_queued_job(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test-delete-queue.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    temp_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(crawl_job_module, "SessionLocal", temp_session)

    # 1. Enqueue job 1 and job 2
    job1 = crawl_job_service.enqueue(source_id="source-1", timeframe="1_day", trigger="TEST1")
    job2 = crawl_job_service.enqueue(source_id="source-2", timeframe="1_day", trigger="TEST2")

    # 2. Claim job 1
    claimed1 = crawl_job_service.claim_next("worker-test")
    assert claimed1.id == job1.id

    # 3. Delete active job 1
    deleted = crawl_job_service.delete_active()
    assert deleted is True

    # Job 1 is gone
    assert crawl_job_service.get_job_status(job1.id) is None

    # 4. Worker claims next -> must get job 2!
    claimed2 = crawl_job_service.claim_next("worker-test")
    assert claimed2 is not None
    assert claimed2.id == job2.id
    assert claimed2.status == CrawlJobStatusEnum.RUNNING


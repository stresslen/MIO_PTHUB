import datetime
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, SessionLocal
from app.models.lead import Lead, ActionEnum
from app.models.organization import Organization, OrganizationContact, OrganizationEvidence


import pytest


def setup_test_db():
    init_db()
    db = SessionLocal()
    organization = Organization(
        id="test-org-1234", legal_name="UBND TP. Hà Nội",
        official_url="https://hanoi.gov.vn/", domain="hanoi.gov.vn",
        organization_type="government", industry="Quản lý nhà nước",
        profile_status="PROFILE_INCOMPLETE", missing_information=["contacts"],
        source_urls=["https://hanoi.gov.vn/"],
    )
    db.merge(organization)
    # Add a sample test lead
    lead = Lead(
        id="test-lead-1234",
        source="baodauthau",
        source_url="https://baodauthau.vn/test-item-post1.html",
        title="Gói thầu xây dựng hệ thống trợ lý ảo phục vụ tiếp dân",
        organization_name="UBND TP. Hà Nội",
        organization_type="government",
        need_summary="Xây dựng Voice AI và chatbot thông minh.",
        need_categories=["Voice AI / Trợ lý giọng nói", "LLM / AI / Trí tuệ nhân tạo"],
        budget_value=4_200_000_000.0,
        budget_text="4.2 tỷ VNĐ",
        location="Hà Nội",
        score=92,
        recommended_action="CALL",
        score_reasons=["+25 Có gói thầu cụ thể", "+20 Ngân sách 4.2 tỷ", "+10 Hà Nội", "+15 Match Voice AI"],
        content_fingerprint="test_fingerprint_hash_12345",
        status="NEW",
        organization_id="test-org-1234",
        enrichment_status="PROFILE_INCOMPLETE",
    )
    db.merge(lead)
    db.commit()
    db.close()


def setup_module(module):
    setup_test_db()


def teardown_module(module):
    """Clean up test lead from database after tests finish."""
    db = SessionLocal()
    test_lead = db.query(Lead).filter(Lead.id == "test-lead-1234").first()
    if test_lead:
        db.delete(test_lead)
    db.query(OrganizationContact).filter(OrganizationContact.organization_id == "test-org-1234").delete()
    db.query(OrganizationEvidence).filter(OrganizationEvidence.organization_id == "test-org-1234").delete()
    organization = db.query(Organization).filter(Organization.id == "test-org-1234").first()
    if organization:
        db.delete(organization)
    db.commit()
    db.close()


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_get_leads_api():
    client = TestClient(app)
    resp = client.get("/api/leads")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


def test_filter_leads_by_action():
    client = TestClient(app)
    resp = client.get("/api/leads?action=CALL")
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["recommended_action"] == "CALL"


def test_get_lead_detail_api():
    client = TestClient(app)
    resp = client.get("/api/leads/test-lead-1234")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-lead-1234"
    assert data["organization_name"] == "UBND TP. Hà Nội"
    assert data["score"] == 92
    assert data["company_profile"]["official_url"] == "https://hanoi.gov.vn/"
    assert data["company_profile"]["profile_status"] == "PROFILE_INCOMPLETE"


def test_removed_stats_and_crawl_history_endpoints():
    client = TestClient(app)
    assert client.get("/api/stats").status_code == 404
    assert client.get("/api/crawl/runs").status_code == 404


def test_sources_api():
    client = TestClient(app)
    resp = client.get("/api/sources")
    assert resp.status_code == 200
    sources = resp.json()
    assert len(sources) == 11
    assert all(source["base_url"].startswith("https://") for source in sources)
    assert all("total_leads_count" in source for source in sources)


def test_export_csv_api():
    client = TestClient(app)
    resp = client.get("/api/export/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "Điểm số" in resp.text


def test_scheduler_status_uses_vietnam_display_time():
    from app.services.scheduler_service import SchedulerService

    service = SchedulerService()
    service.hour = 14
    service.minute = 30
    service.cadence = "daily"
    service._calculate_next_run()
    status = service.get_status()
    assert status["schedule_label"] == "14:30 hàng ngày"
    assert status["next_run_display"].startswith("14:30:00 ")


def test_manual_crawl_timeframe_validation():
    client = TestClient(app)
    response = client.post(
        "/api/crawl/run?sync=false",
        json={"source_id": "baodauthau", "timeframe": "invalid"},
    )
    assert response.status_code == 422


def test_timeframe_cutoffs_are_exact_vietnam_local_windows():
    import datetime
    import pytest
    from app.services.crawler_service import calculate_since_datetime

    now = datetime.datetime(2026, 8, 23, 14, 30)
    assert calculate_since_datetime("1_day", now) == now - datetime.timedelta(days=1)
    assert calculate_since_datetime("1_week", now) == now - datetime.timedelta(days=7)
    assert calculate_since_datetime("1_month", now) == now - datetime.timedelta(days=30)
    with pytest.raises(ValueError):
        calculate_since_datetime("all", now)


def test_missing_publication_date_falls_back_to_crawl_time():
    from app.services.crawler_service import publication_or_crawl_time

    crawled_at = datetime.datetime(2026, 8, 23, 15, 20, 30)
    published_at = datetime.datetime(2026, 8, 22, 8, 10)

    assert publication_or_crawl_time(None, crawled_at) == crawled_at
    assert publication_or_crawl_time(published_at, crawled_at) == published_at


def test_scheduler_ignores_old_weekly_monthly_fields():
    from app.services.scheduler_service import SchedulerService

    service = SchedulerService()
    service._apply_config({
        "enabled": True,
        "hour": 15,
        "minute": 45,
        "cadence": "weekly",
        "weekday": 4,
        "timeframe": "1_month",
    })
    assert service.cadence == "daily"
    assert service.timeframe == "1_day"
    assert service.hour == 15
    assert service.minute == 45

async def test_scheduler_start_does_not_bootstrap_historical_data(monkeypatch):
    import asyncio
    from app.services.scheduler_service import SchedulerService

    service = SchedulerService()
    service.enabled = True
    runs = []

    async def record_run(*args, **kwargs):
        runs.append((args, kwargs))

    monkeypatch.setattr(service, "_execute_run", record_run)
    service.start()
    await asyncio.sleep(0.01)
    service.stop()

    assert runs == []


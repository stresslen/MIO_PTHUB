import datetime
import json
from types import SimpleNamespace


import pytest

from app.config import get_sources_config, settings
from app.crawlers.base import RawDocument
from app.crawlers.generic import GenericWebsiteAdapter
from app.pipeline.extract import AIAuthenticationError, AIExtractor
from app.services.source_service import (
    ERROR_NOTICE,
    SourceService,
    normalize_source_url,
    validate_public_url,
)


class FakeSourceSheets:
    configured = True

    def __init__(self):
        self.rows = []

    def seed_source_rows(self, rows):
        if self.rows:
            return 0
        self.rows = [dict(row) for row in rows]
        return len(self.rows)

    def get_source_rows(self):
        return [dict(row) for row in self.rows]

    def upsert_source_row(self, item):
        for index, row in enumerate(self.rows):
            if row["id"] == item["id"]:
                self.rows[index] = dict(item)
                return True
        self.rows.append(dict(item))
        return True


def test_source_bootstrap_moves_all_yaml_urls_to_google_sheets_cache():
    sheets = FakeSourceSheets()
    service = SourceService(sheets)
    result = service.bootstrap()

    yaml_sources = get_sources_config()["sources"]
    expected_urls = {
        normalize_source_url(url)
        for source in yaml_sources
        for url in source.get("seed_urls", [])
    }
    stored_urls = {
        url
        for source in result["items"]
        for url in source["seed_urls"]
    }

    assert result["source"] == "google_sheets"
    assert result["total"] == 12
    assert stored_urls == expected_urls
    assert all(row["adapter_mode"] == "specialized" for row in sheets.rows)


def test_bootstrap_migrates_existing_topcv_search_url_to_root():
    sheets = FakeSourceSheets()
    service = SourceService(sheets)
    sheets.rows = [dict(row) for row in service._rows]
    topcv = next(row for row in sheets.rows if row["id"] == "topcv")
    topcv["seed_urls"] = json.dumps([
        "https://www.topcv.vn/tim-viec-lam-chuyen-doi-so?type_keyword=1&sba=1"
    ])
    topcv["enabled"] = False

    result = service.bootstrap()
    migrated = next(row for row in result["items"] if row["id"] == "topcv")

    assert migrated["seed_urls"] == ["https://www.topcv.vn/"]
    assert migrated["enabled"] is False
    assert migrated["adapter_key"] == "topcv"


def test_failed_custom_url_is_still_saved_for_later_update(monkeypatch):
    import app.services.source_service as source_module

    sheets = FakeSourceSheets()
    service = SourceService(sheets)
    service.bootstrap()
    monkeypatch.setattr(
        source_module,
        "validate_public_url",
        lambda url, resolve_dns=True: (False, "Không phân giải được domain"),
    )

    result = service.add_url("Nguồn thử nghiệm", "https://khong-ton-tai.invalid")

    saved = result["items"][0]
    assert result["added"] == 1
    assert result["needs_update"] == 1
    assert saved["status"] == "NEEDS_ADAPTER"
    assert saved["enabled"] is False
    assert saved["name"] == "Nguồn thử nghiệm"
    assert saved["last_error"] == ERROR_NOTICE
    assert any(row["id"] == saved["id"] for row in sheets.rows)


def test_custom_source_accepts_exactly_one_url():
    sheets = FakeSourceSheets()
    service = SourceService(sheets)
    service.bootstrap()

    with pytest.raises(ValueError, match="một URL"):
        service.add_url(
            "Hai nguồn",
            "https://example.test/one\nhttps://example.test/two",
        )


def test_private_network_urls_are_blocked():
    valid, reason = validate_public_url("http://127.0.0.1/admin")
    assert valid is False
    assert "nội bộ" in reason


@pytest.mark.asyncio
async def test_generic_crawler_discovers_same_domain_and_cleans_html(monkeypatch):
    source = {
        "id": "custom-example",
        "name": "example.test",
        "seed_urls": ["https://example.test/"],
        "rate_limit_delay": 0,
        "timeout": 5,
    }
    adapter = GenericWebsiteAdapter(source)
    documents = {
        "https://example.test/sitemap.xml": """<urlset><url><loc>https://example.test/news</loc></url></urlset>""",
        "https://example.test/": """
            <html><head><title>Trang chủ</title><script>window.secret = 1</script></head>
            <body><header>Hotline: 028 1234 5678</header><nav>Menu không cần AI</nav><main><h1>Nhu cầu chuyển đổi số</h1>
            <p>Doanh nghiệp đang tìm giải pháp quản lý dữ liệu và triển khai phần mềm.</p>
            <a href="mailto:contact@example.test">Email doanh nghiệp</a>
            <a href="tel:+842812345678">Gọi ngay</a><a href="/news">Tin tức</a><a href="https://outside.test/page">Ngoài domain</a>
            </main><footer>Email: info@example.test | Địa chỉ văn phòng</footer></body></html>
        """,
        "https://example.test/news": """
            <html><head><title>Tin dự án</title></head><body><article>
            <h1>Dự án trung tâm dữ liệu</h1><p>Nội dung dự án đủ dài để hệ thống chuyển
            sang Gemini phân tích nhu cầu, đơn vị và thông tin liên hệ công khai.</p>
            </article><script>alert('remove me')</script></body></html>
        """,
    }

    async def fake_fetch(url):
        html = documents[url]
        return RawDocument(
            url=url,
            source_id=adapter.source_id,
            fetched_at=datetime.datetime(2026, 8, 25),
            html=html,
            text=html,
            headers={"Content-Type": "text/html"},
        )

    monkeypatch.setattr(adapter, "fetch", fake_fetch)
    urls = await adapter.discover(max_items=20)
    parsed = await adapter.parse(await fake_fetch("https://example.test/"))

    assert urls == ["https://example.test/", "https://example.test/news"]
    assert "window.secret" not in parsed.raw_content
    assert "Menu không cần AI" in parsed.raw_content
    assert "Hotline: 028 1234 5678" in parsed.raw_content
    assert "Email: info@example.test" in parsed.raw_content
    assert "Email: contact@example.test" in parsed.raw_content
    assert "SĐT: +842812345678" in parsed.raw_content
    assert "Nhu cầu chuyển đổi số" in parsed.raw_content
    assert all("outside.test" not in url for url in urls)


def test_ai_extraction_never_falls_back_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", None)

    with pytest.raises(AIAuthenticationError):
        AIExtractor().extract("Tiêu đề", "Nội dung đủ dài để xử lý")



def test_source_import_api_saves_then_queues_worker_probe(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import sources as sources_api

    pending = {
        "id": "custom-api-test",
        "name": "example.test",
        "description": "Nguồn website do người dùng thêm",
        "seed_urls": ["https://example.test/"],
        "adapter_mode": "generic",
        "adapter_key": "generic",
        "crawl_scope": "full_site",
        "rate_limit_delay": 1.0,
        "timeout": 10,
        "enabled": True,
        "include_in_schedule": False,
        "status": "NEW",
        "last_error": "",
        "last_attempt_at": "",
        "last_success_at": "",
        "created_at": "",
        "updated_at": "",
    }
    monkeypatch.setattr(
        sources_api.source_service,
        "add_url",
        lambda name, url, include_in_schedule=False: {
            "added": 1,
            "duplicates": 0,
            "needs_update": 0,
            "items": [pending],
            "total": 11,
        },
    )
    monkeypatch.setattr(
        sources_api.source_service,
        "probe",
        lambda source_id: (_ for _ in ()).throw(AssertionError("API must not run browser probe")),
    )
    monkeypatch.setattr(
        sources_api.crawl_job_service,
        "enqueue",
        lambda **kwargs: SimpleNamespace(id="queued-source-job"),
    )

    response = TestClient(app).post(
        "/api/sources/import",
        json={"name": "Trang thử nghiệm", "url": "https://example.test", "include_in_schedule": False},
    )

    assert response.status_code == 200
    assert response.json()["added"] == 1
    assert response.json()["needs_update"] == 0
    assert response.json()["items"][0]["status"] == "NEW"
    assert response.json()["queued_job_ids"] == ["queued-source-job"]

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.pipeline.extract import AIExtractor
from app.services.xah_search_service import xah_search_service


def test_gemini_calls_xah_only_when_information_is_missing(monkeypatch):
    extractor = AIExtractor()
    responses = iter([
        {
            "organization_name": "UBND tỉnh A",
            "organization_type": "government",
            "need_summary": "Triển khai nền tảng AI.",
            "need_categories": ["LLM / AI / Trí tuệ nhân tạo"],
            "relevance": 0.8,
            "evidence": ["Thông tin gốc"],
            "needs_web_search": True,
            "missing_information": ["ngân sách"],
            "search_query": "UBND tỉnh A dự án AI ngân sách",
        },
        {
            "organization_name": "UBND tỉnh A",
            "organization_type": "government",
            "need_summary": "Triển khai nền tảng AI với ngân sách đã công bố.",
            "need_categories": ["LLM / AI / Trí tuệ nhân tạo"],
            "budget_value": 1000000000,
            "budget_text": "1 tỷ đồng",
            "relevance": 0.9,
            "evidence": ["Ngân sách 1 tỷ đồng - https://example.com/source"],
        },
    ])
    monkeypatch.setattr(settings, "xah_api_key", "test-key")
    monkeypatch.setattr(extractor, "_call_gemini_json", lambda prompt: next(responses))
    monkeypatch.setattr(xah_search_service, "search", lambda query: {
        "query": query,
        "answer": "Dự án có ngân sách 1 tỷ đồng.",
        "results": [{"title": "Nguồn", "url": "https://example.com/source", "snippet": "Ngân sách 1 tỷ đồng"}],
        "provider": "test",
    })

    result = extractor._extract_gemini("Dự án AI", "Nội dung chưa đủ")
    assert result.web_search_used is True
    assert result.budget_value == 1000000000
    assert result.search_sources == ["https://example.com/source"]
    assert any("https://example.com/source" in item for item in result.evidence)


def test_gemini_skips_xah_when_information_is_sufficient(monkeypatch):
    extractor = AIExtractor()
    monkeypatch.setattr(settings, "xah_api_key", "test-key")
    monkeypatch.setattr(extractor, "_call_gemini_json", lambda prompt: {
        "organization_name": "Sở Thông tin và Truyền thông",
        "organization_type": "government",
        "need_summary": "Mua sắm hệ thống OCR.",
        "need_categories": ["OCR / Số hóa tài liệu"],
        "relevance": 0.9,
        "evidence": ["Mua sắm hệ thống OCR"],
        "needs_web_search": False,
        "missing_information": [],
        "search_query": None,
    })

    def unexpected_search(query):
        raise AssertionError("XAH must not run when Gemini says data is sufficient")

    monkeypatch.setattr(xah_search_service, "search", unexpected_search)
    result = extractor._extract_gemini("Gói OCR", "Nội dung đầy đủ")
    assert result.web_search_used is False


def test_public_search_api_is_removed():
    paths = set(app.openapi()["paths"])
    assert "/api/search/ask" not in paths
    assert "/api/search/raw" not in paths


def test_storage_status_never_exposes_credentials():
    body = TestClient(app).get("/api/storage/status").json()
    serialized = str(body).lower()
    assert "private_key" not in serialized
    assert "xah_api_key" not in serialized

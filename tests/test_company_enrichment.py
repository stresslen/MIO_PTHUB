import pytest

from app.config import settings
from app.services.company_enrichment_service import CompanyEnrichmentService


def complete_profile(source_url="https://abc.vn/gioi-thieu"):
    return {
        "legal_name": "Công ty ABC",
        "industry": "Công nghệ thông tin",
        "size": "Doanh nghiệp vừa",
        "locations": ["Hà Nội"],
        "employee_count": "100-200",
        "technologies": ["Cloud"],
        "projects": [{"name": "Nền tảng số", "summary": "Đang triển khai", "source_url": source_url}],
        "news": [], "jobs": [], "tenders": [],
        "contacts": [{
            "full_name": "Nguyễn Văn A", "raw_title": "Giám đốc CNTT",
            "role_group": "technical_buyer", "email": "a@abc.vn", "phone": "+84 912 345 678",
            "source_url": source_url, "evidence_text": "Ông Nguyễn Văn A là Giám đốc CNTT",
            "decision_score": 88, "decision_reason": "Phụ trách CNTT",
        }],
        "evidence": [{
            "field": "industry", "value": "Công nghệ thông tin", "source_url": source_url,
            "evidence_text": "Hoạt động trong lĩnh vực công nghệ thông tin", "confidence": 0.95,
        }],
        "missing_information": [],
    }


@pytest.mark.asyncio
async def test_round_two_complete_profile_does_not_call_xah(monkeypatch):
    service = CompanyEnrichmentService()
    monkeypatch.setattr(settings, "company_enrichment_enabled", True)
    monkeypatch.setattr(settings, "company_enrichment_mode", "xah")
    monkeypatch.setattr(
        "app.services.company_enrichment_service.validate_public_url",
        lambda url, resolve_dns=True: (True, None),
    )

    async def crawl(url):
        return "URL: https://abc.vn/gioi-thieu\\nNội dung có hồ sơ", ["https://abc.vn/gioi-thieu"], []

    monkeypatch.setattr(service, "_crawl_official_site", crawl)
    monkeypatch.setattr("app.services.company_enrichment_service.ai_extractor._call_gemini_json", lambda prompt: complete_profile())
    monkeypatch.setattr(service, "_search_queries", lambda queries: (_ for _ in ()).throw(AssertionError("Không được gọi XAH")))

    result = await service.enrich("Công ty ABC", "enterprise", "https://abc.vn", None, "Hà Nội")
    assert result.status == "COMPLETE"
    assert result.xah_used is False
    assert result.contacts[0]["phone"] == "0912345678"


@pytest.mark.asyncio
async def test_missing_profile_calls_xah_and_loads_result_urls(monkeypatch):
    service = CompanyEnrichmentService()
    monkeypatch.setattr(settings, "company_enrichment_enabled", True)
    monkeypatch.setattr(settings, "company_enrichment_mode", "xah")
    monkeypatch.setattr(settings, "xah_api_key", "test-key")
    monkeypatch.setattr(
        "app.services.company_enrichment_service.validate_public_url",
        lambda url, resolve_dns=True: (True, None),
    )

    async def crawl(url):
        return "URL: https://abc.vn\\nNội dung chưa đủ", ["https://abc.vn/"], []

    calls = iter([
        {"legal_name": "Công ty ABC", "missing_information": ["contacts", "technologies"]},
        complete_profile("https://news.example.com/abc-profile"),
    ])
    loaded = []
    monkeypatch.setattr(service, "_crawl_official_site", crawl)
    monkeypatch.setattr(service, "_make_queries", lambda *args: ['"Công ty ABC" CIO công nghệ'])
    monkeypatch.setattr(service, "_search_queries", lambda queries: ([{
        "url": "https://news.example.com/abc-profile", "title": "Hồ sơ ABC", "snippet": "Giám đốc CNTT"
    }], []))

    def load_urls(results):
        loaded.extend(item["url"] for item in results)
        return ([{"url": results[0]["url"], "title": "Hồ sơ ABC", "text": "Thông tin CIO và công nghệ"}], [])

    monkeypatch.setattr(service, "_load_search_urls", load_urls)
    monkeypatch.setattr("app.services.company_enrichment_service.ai_extractor._call_gemini_json", lambda prompt: next(calls))

    result = await service.enrich("Công ty ABC", "enterprise", "https://abc.vn", None, "Hà Nội")
    assert loaded == ["https://news.example.com/abc-profile"]
    assert result.xah_used is True
    assert result.status == "COMPLETE"
    assert "https://news.example.com/abc-profile" in result.source_urls


@pytest.mark.asyncio
async def test_missing_round_one_url_sends_keywords_to_xah_without_direct_crawl(monkeypatch):
    service = CompanyEnrichmentService()
    monkeypatch.setattr(settings, "company_enrichment_enabled", True)
    monkeypatch.setattr(settings, "company_enrichment_mode", "xah")
    monkeypatch.setattr(settings, "xah_api_key", "test-key")

    generated_targets = []
    monkeypatch.setattr(
        service,
        "_make_queries",
        lambda name, tax_code, location, targets: (
            generated_targets.extend(targets) or ['"Công ty ABC" hồ sơ công ty người liên hệ']
        ),
    )
    xah_url = "https://directory.example.com/cong-ty-abc"
    monkeypatch.setattr(service, "_search_queries", lambda queries: ([{
        "url": xah_url,
        "title": "Hồ sơ Công ty ABC",
        "snippet": "Công ty ABC hoạt động trong lĩnh vực CNTT; Giám đốc CNTT là Nguyễn Văn A.",
        "query": queries[0],
        "xah_answer": "XAH tìm thấy hồ sơ và người liên hệ của Công ty ABC.",
        "published_at": None,
    }], []))

    async def unexpected_crawl(url):
        raise AssertionError("Không được crawl website trực tiếp khi vòng 1 không có URL")

    monkeypatch.setattr(service, "_crawl_official_site", unexpected_crawl)
    monkeypatch.setattr(
        service,
        "_load_search_urls",
        lambda results: (_ for _ in ()).throw(
            AssertionError("Nhánh không URL phải dùng trực tiếp dữ liệu XAH")
        ),
    )
    prompts = []
    profile_data = complete_profile(xah_url)
    profile_data["official_url"] = xah_url

    def extract_profile(prompt):
        prompts.append(prompt)
        return profile_data

    monkeypatch.setattr(
        "app.services.company_enrichment_service.ai_extractor._call_gemini_json",
        extract_profile,
    )

    result = await service.enrich("Công ty ABC", "enterprise", None, None, "Hà Nội")

    assert "official_url" in generated_targets
    assert len(prompts) == 1
    assert "KẾT QUẢ XAH SEARCH CÓ URL NGUỒN" in prompts[0]
    assert "Đoạn nội dung XAH thu thập" in prompts[0]
    assert result.status == "COMPLETE"
    assert result.xah_used is True
    assert result.organization["official_url"] == xah_url
    assert result.source_urls == [xah_url]


@pytest.mark.asyncio
async def test_failed_second_crawl_uses_xah_without_fake_data(monkeypatch):
    service = CompanyEnrichmentService()
    monkeypatch.setattr(settings, "company_enrichment_enabled", True)
    monkeypatch.setattr(settings, "company_enrichment_mode", "xah")
    monkeypatch.setattr(settings, "xah_api_key", "test-key")
    monkeypatch.setattr(
        "app.services.company_enrichment_service.validate_public_url",
        lambda url, resolve_dns=True: (True, None),
    )

    async def failed_crawl(url):
        raise RuntimeError("SECOND_CRAWL_BLOCKED")

    monkeypatch.setattr(service, "_crawl_official_site", failed_crawl)
    monkeypatch.setattr(service, "_make_queries", lambda *args: ['"Công ty ABC" hồ sơ'])
    monkeypatch.setattr(service, "_search_queries", lambda queries: ([], []))
    monkeypatch.setattr(service, "_load_search_urls", lambda results: ([], []))

    result = await service.enrich("Công ty ABC", "enterprise", "https://abc.vn", None, None)
    assert result.status == "SECOND_CRAWL_BLOCKED"
    assert result.organization["industry"] is None
    assert "SECOND_CRAWL_BLOCKED" in (result.message or "")
    assert result.xah_used is True


def test_unseen_source_url_is_rejected_from_profile():
    service = CompanyEnrichmentService()
    profile, contacts, evidence, missing = service._normalize_profile(
        complete_profile("https://invented.example/fake"),
        "Công ty ABC", "https://abc.vn/", ["https://abc.vn/gioi-thieu"],
    )
    assert profile["projects"] == []
    assert contacts == []
    assert evidence == []
    assert "contacts" in missing

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
async def test_missing_profile_calls_xah_and_crawls_official_site(monkeypatch):
    service = CompanyEnrichmentService()
    monkeypatch.setattr(settings, "company_enrichment_enabled", True)
    monkeypatch.setattr(settings, "company_enrichment_mode", "xah")
    monkeypatch.setattr(settings, "xah_api_key", "test-key")

    xah_url = "https://abc.example.com"
    crawled = []
    calls = iter([complete_profile(xah_url)])

    async def crawl(url):
        crawled.append(url)
        return "URL: https://abc.example.com\nNội dung hồ sơ đầy đủ", [xah_url], []

    monkeypatch.setattr(service, "_crawl_official_site", crawl)
    monkeypatch.setattr(service, "_make_queries", lambda *args: ['"Công ty ABC" website chính thức'])
    monkeypatch.setattr(service, "_search_queries", lambda queries: ([{
        "url": xah_url, "title": "Công ty ABC", "snippet": "Công ty ABC"
    }], []))
    monkeypatch.setattr(
        "app.services.company_enrichment_service.ai_extractor._call_gemini_json",
        lambda prompt: next(calls),
    )

    result = await service.enrich("Công ty ABC", "enterprise", None, None, "Hà Nội")

    assert crawled == [xah_url]
    assert result.xah_used is True
    assert result.status == "COMPLETE"
    assert xah_url in result.source_urls


@pytest.mark.asyncio
async def test_missing_round_one_url_crawls_result_urls_before_gemini(monkeypatch):
    service = CompanyEnrichmentService()
    monkeypatch.setattr(settings, "company_enrichment_enabled", True)
    monkeypatch.setattr(settings, "company_enrichment_mode", "xah")
    monkeypatch.setattr(settings, "xah_api_key", "test-key")

    generated_targets = []
    monkeypatch.setattr(
        service,
        "_make_queries",
        lambda name, tax_code, location, targets: (
            generated_targets.extend(targets) or ['"Công ty ABC" website chính thức']
        ),
    )
    xah_url = "https://directory.example.com/cong-ty-abc"
    monkeypatch.setattr(service, "_search_queries", lambda queries: ([{
        "url": xah_url,
        "title": "Hồ sơ Công ty ABC",
        "snippet": "Công ty ABC hoạt động trong lĩnh vực CNTT",
        "query": queries[0],
        "xah_answer": "XAH tìm thấy website chính thức của Công ty ABC.",
        "published_at": None,
    }], []))

    crawled = []

    async def crawl(url):
        crawled.append(url)
        return (
            "URL: https://directory.example.com/cong-ty-abc\n"
            "Nội dung đầy đủ về CIO, công nghệ và dự án của Công ty ABC",
            [xah_url, "https://directory.example.com/gioi-thieu"],
            [],
        )

    monkeypatch.setattr(service, "_crawl_official_site", crawl)
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

    result = await service.enrich(
        "Công ty ABC", "enterprise", None, None, "Hà Nội",
        round_one_context="{\"need_summary\":\"Nhu cầu chuyển đổi số\"}",
    )

    assert "official_url" in generated_targets
    assert len(prompts) == 1
    assert crawled == [xah_url]
    assert "DỮ LIỆU CRAWL WEBSITE CHÍNH THỨC" in prompts[0]
    assert "DỮ LIỆU ĐÃ TRÍCH XUẤT Ở VÒNG 1" in prompts[0]
    assert "Nhu cầu chuyển đổi số" in prompts[0]
    assert "Nội dung đầy đủ về CIO" in prompts[0]
    assert result.status == "COMPLETE"
    assert result.xah_used is True
    assert result.organization["official_url"] == "https://directory.example.com/"
    assert "https://directory.example.com/gioi-thieu" in result.source_urls


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


@pytest.mark.asyncio
async def test_xah_retries_until_a_new_url_crawls(monkeypatch):
    service = CompanyEnrichmentService()
    monkeypatch.setattr(settings, "company_enrichment_enabled", True)
    monkeypatch.setattr(settings, "company_enrichment_mode", "xah")
    monkeypatch.setattr(settings, "xah_api_key", "test-key")
    monkeypatch.setattr(settings, "company_xah_retry_attempts", 5)
    monkeypatch.setattr(
        service,
        "_make_queries",
        lambda *args: ["website chính thức Công ty ABC"],
    )

    urls = [f"https://candidate-{index}.example.com" for index in range(1, 6)]
    search_calls = []
    crawled = []

    def search(queries):
        url = urls[len(search_calls)]
        search_calls.append(url)
        return ([{"url": url, "title": "Công ty ABC", "snippet": ""}], [])

    async def crawl(url):
        crawled.append(url)
        if url != urls[-1]:
            raise RuntimeError(f"{url}: crawl failed")
        return (
            "URL: https://candidate-5.example.com/\n"
            "Thông tin đầy đủ về Công ty ABC và công nghệ đang sử dụng",
            [url],
            [],
        )

    profile = complete_profile(urls[-1])
    profile["official_url"] = urls[-1]
    monkeypatch.setattr(service, "_search_queries", search)
    monkeypatch.setattr(service, "_crawl_official_site", crawl)
    monkeypatch.setattr(
        "app.services.company_enrichment_service.ai_extractor._call_gemini_json",
        lambda prompt: profile,
    )

    result = await service.enrich("Công ty ABC", "enterprise", None, None, "Hà Nội")

    assert search_calls == urls
    assert crawled == urls
    assert result.status == "COMPLETE"
    assert result.organization["official_url"] == "https://candidate-5.example.com/"
    assert urls[-1] in result.source_urls


@pytest.mark.asyncio
async def test_xah_search_results_ignore_search_engine_urls(monkeypatch):
    from app.services.company_enrichment_service import CompanyEnrichmentService

    service = CompanyEnrichmentService()
    monkeypatch.setattr(
        "app.services.company_enrichment_service.xah_search_service.search",
        lambda _query: {
            "answer": "",
            "results": [
                {"url": "https://www.google.com/search?q=upbase", "title": "Google"},
                {"url": "https://www.upbase.vn/vi", "title": "Upbase"},
            ],
        },
    )

    results, errors = service._search_queries(["website chính thức Upbase"])

    assert errors == []
    assert [item["url"] for item in results] == ["https://www.upbase.vn/vi"]

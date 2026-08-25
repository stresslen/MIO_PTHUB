import datetime

from app.crawlers.base import RawDocument
from app.crawlers.topcv import TopCVAdapter


def test_topcv_keyword_slug_and_job_url_extraction():
    adapter = TopCVAdapter()
    html = """
    <a href="/viec-lam/chuyen-vien-chuyen-doi-so/123456.html?tracking=home">Tin 1</a>
    <a href="https://www.topcv.vn/viec-lam/chuyen-vien-chuyen-doi-so/123456.html">Trùng</a>
    <a href="https://evil.example/viec-lam/sai/999.html">Sai domain</a>
    """

    assert adapter._slugify_keyword("Chuyển đổi số") == "chuyen-doi-so"
    assert adapter._extract_job_urls(html, "https://www.topcv.vn/") == [
        "https://www.topcv.vn/viec-lam/chuyen-vien-chuyen-doi-so/123456.html"
    ]


def test_topcv_builds_search_url_from_each_hyphenated_keyword(monkeypatch):
    adapter = TopCVAdapter()
    monkeypatch.setattr(
        adapter,
        "_discovery_search_keywords",
        lambda max_items=None: ["chuyển đổi số", "trí tuệ nhân tạo"],
    )

    assert adapter.seed_urls == ["https://www.topcv.vn/"]
    assert adapter._search_urls() == [
        "https://www.topcv.vn/tim-viec-lam-chuyen-doi-so?type_keyword=1&sba=1",
        "https://www.topcv.vn/tim-viec-lam-tri-tue-nhan-tao?type_keyword=1&sba=1",
    ]


def test_topcv_run_config_uses_proxy_only_when_configured(monkeypatch):
    adapter = TopCVAdapter()
    _, _, CacheMode, CrawlerRunConfig, _, _ = adapter._crawl4ai_types()

    monkeypatch.setattr("app.crawlers.topcv.settings.topcv_proxy_url", None)
    direct = adapter._run_config(CrawlerRunConfig, CacheMode, listing=True)
    assert direct.proxy_config is None
    assert direct.max_retries == 0

    monkeypatch.setattr("app.crawlers.topcv.settings.topcv_proxy_url", "http://user:pass@proxy.test:8080")
    proxied = adapter._run_config(CrawlerRunConfig, CacheMode, listing=True)
    assert proxied.proxy_config.server == "http://proxy.test:8080"
    assert proxied.max_retries == 1


async def test_topcv_parser_prefers_jobposting_schema_date_and_company():
    html = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Chuyên viên Chuyển đổi số",
        "datePosted": "2026-08-24",
        "hiringOrganization": {"@type": "Organization", "name": "Công ty ABC"}
      }
      </script>
      <main>
        <h1>Tiêu đề giao diện</h1>
        <section class="job-description">
          Công ty cần chuyên viên triển khai các dự án chuyển đổi số, phân tích quy trình,
          phối hợp ứng dụng công nghệ và quản trị dữ liệu cho toàn bộ doanh nghiệp.
        </section>
      </main>
    </body></html>
    """
    adapter = TopCVAdapter()
    parsed = await adapter.parse(RawDocument(
        url="https://www.topcv.vn/viec-lam/chuyen-vien-chuyen-doi-so/123456.html",
        source_id="topcv",
        fetched_at=datetime.datetime(2026, 8, 25),
        html=html,
        text="",
    ))

    assert parsed.title == "Chuyên viên Chuyển đổi số"
    assert parsed.author == "Công ty ABC"
    assert parsed.published_at == datetime.datetime(2026, 8, 24)
    assert "Đơn vị tuyển dụng: Công ty ABC" in parsed.raw_content
    assert parsed.extra_metadata["adapter"] == "topcv_crawl4ai_playwright"

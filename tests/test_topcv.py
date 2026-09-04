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
    _, _, CacheMode, CrawlerRunConfig = adapter._crawl4ai_types()

    monkeypatch.setattr("app.crawlers.topcv.settings.topcv_proxy_url", None)
    direct = adapter._run_config(CrawlerRunConfig, CacheMode, listing=True)
    assert direct.proxy_config is None
    assert direct.max_retries == 0

    monkeypatch.setattr("app.crawlers.topcv.settings.topcv_proxy_url", "http://user:pass@proxy.test:8080")
    proxied = adapter._run_config(CrawlerRunConfig, CacheMode, listing=True)
    assert proxied.proxy_config.server == "http://proxy.test:8080"
    assert proxied.max_retries == 1


def test_topcv_uses_persistent_profile_per_url_and_zero_delay_config():
    adapter = TopCVAdapter()
    _, BrowserConfig, CacheMode, CrawlerRunConfig = adapter._crawl4ai_types()
    first_url = "https://www.topcv.vn/viec-lam/nhan-vien-admin/2083082.html"
    second_url = "https://www.topcv.vn/viec-lam/accountant/2271897.html"

    first = adapter._browser_config(BrowserConfig, first_url)
    second = adapter._browser_config(BrowserConfig, second_url)
    run = adapter._run_config(CrawlerRunConfig, CacheMode, listing=False)

    assert first.browser_type == "chromium"
    assert first.headless is True
    assert first.java_script_enabled is True
    assert first.use_persistent_context is True
    assert "topcv-zero-delay-" in first.user_data_dir
    assert first.user_data_dir != second.user_data_dir
    assert run.wait_until == "commit"
    assert run.page_timeout == 30_000
    assert run.delay_before_return_html == 3.0


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


async def test_topcv_discover_crawls_each_keyword_before_next_search(monkeypatch):
    adapter = TopCVAdapter()
    search_urls = [
        "https://www.topcv.vn/tim-viec-lam-chuyen-doi-so?type_keyword=1&sba=1",
        "https://www.topcv.vn/tim-viec-lam-tri-tue-nhan-tao?type_keyword=1&sba=1",
    ]
    listing_html = {
        search_urls[0]: """
        <div class='job-item'><h3><a href='/viec-lam/ba-chuyen-doi-so/1001.html'>BA chuyển đổi số</a></h3><div class='company'>Công ty A</div><span>Hôm nay</span></div>
        """,
        search_urls[1]: """
        <div class='job-item'><h3><a href='/viec-lam/ky-su-ai/1002.html'>Kỹ sư AI</a></h3><div class='company'>Công ty B</div><span>Hôm nay</span></div>
        """,
    }
    detail_urls = [
        "https://www.topcv.vn/viec-lam/ba-chuyen-doi-so/1001.html",
        "https://www.topcv.vn/viec-lam/ky-su-ai/1002.html",
    ]
    events = []

    monkeypatch.setattr(
        adapter,
        "_crawl4ai_types",
        lambda: (object, object, object, object),
    )
    monkeypatch.setattr(adapter, "_run_config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(adapter, "_search_urls", lambda max_queries=3: search_urls)
    async def fake_crawl(url, _config):
        events.append(url)
        html = listing_html.get(url)
        if html is None:
            title = "BA chuyển đổi số" if url == detail_urls[0] else "Kỹ sư AI"
            html = f"<main><h1>{title}</h1><p>Mô tả công việc và yêu cầu công nghệ.</p></main>"
        return RawDocument(url=url, source_id="topcv", html=html, text=html)

    monkeypatch.setattr(adapter, "_crawl_url_with_browser", fake_crawl)

    discovered = await adapter.discover()

    assert events == [search_urls[0], detail_urls[0], search_urls[1], detail_urls[1]]
    assert discovered == detail_urls

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

from app.crawlers import get_adapter, get_all_adapters, CRAWLER_REGISTRY
from app.crawlers.base import RawDocument


def test_adapter_registry():
    adapters = get_all_adapters()
    assert len(adapters) == 10
    assert "muasamcong" in adapters
    assert "dauthau_asia" in adapters
    assert "baodauthau" in adapters
    assert "chinhphu" in adapters
    assert "xaydungchinhsach" in adapters
    assert "congbao" in adapters
    assert "most_gov" in adapters
    assert "vietnamnet" in adapters
    assert "vnexpress" in adapters
    assert "hanoi_gov" in adapters


async def test_baodauthau_parser():
    adapter = get_adapter("baodauthau")
    sample_html = """
    <html>
        <head><title>Báo Đấu thầu</title></head>
        <body>
            <h1 class="article-title">Quảng Ninh mời thầu gói số hóa tài liệu đất đai 4,8 tỷ đồng</h1>
            <span class="meta-date">24/08/2026 08:30</span>
            <div class="sapo">Sở TN&MT Quảng Ninh chuẩn bị lựa chọn nhà thầu cho gói thầu số hóa.</div>
            <div class="article-body">
                <p>Nội dung gói thầu bao gồm quét và nhận dạng OCR toàn bộ hồ sơ đất đai.</p>
                <p>Thời điểm đóng thầu: 10/09/2026 09:00.</p>
            </div>
        </body>
    </html>
    """
    raw_doc = RawDocument(
        url="https://baodauthau.vn/thong-bao-moi-thau/bai-viet-post123456.html",
        source_id="baodauthau",
        html=sample_html,
        text="Quảng Ninh mời thầu...",
    )
    parsed = await adapter.parse(raw_doc)

    assert "Quảng Ninh" in parsed.title
    assert "4,8 tỷ" in parsed.title
    assert "OCR" in parsed.raw_content
    assert parsed.published_at is not None
    assert parsed.published_at.year == 2026


async def test_chinhphu_parser():
    adapter = get_adapter("chinhphu")
    sample_html = """
    <html>
        <body>
            <h1 class="detail-title">Phê duyệt đề án phát triển ứng dụng dữ liệu dân cư và AI</h1>
            <div class="publish-date">22/08/2026</div>
            <div class="detail-content">
                <p>Thủ tướng Chính phủ vừa ký quyết định triển khai hạ tầng dữ liệu và trợ lý ảo.</p>
            </div>
        </body>
    </html>
    """
    raw_doc = RawDocument(
        url="https://baochinhphu.vn/phe-duyet-de-an-102260822000000000.htm",
        source_id="chinhphu",
        html=sample_html,
        text="Phê duyệt đề án phát triển...",
    )
    parsed = await adapter.parse(raw_doc)

    assert "Phê duyệt" in parsed.title
    assert "dữ liệu" in parsed.raw_content
    assert parsed.published_at is not None


async def test_muasamcong_parser():
    adapter = get_adapter("muasamcong")
    sample_html = """
    <html>
        <body>
            <h1>Dự án Lựa chọn nhà thầu triển khai nền tảng đô thị thông minh</h1>
            <div>Thời điểm đăng tải: 20/08/2026</div>
            <p>Hệ thống giám sát giao thông thông minh và camera AI trên địa bàn tỉnh.</p>
        </body>
    </html>
    """
    raw_doc = RawDocument(
        url="https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?render=index",
        source_id="muasamcong",
        html=sample_html,
        text="Dự án Lựa chọn nhà thầu...",
    )
    parsed = await adapter.parse(raw_doc)
    assert "nhà thầu" in parsed.title.lower() or "thông minh" in parsed.title.lower()
    assert parsed.published_at is not None


async def test_parser_keeps_unknown_publication_date_empty():
    adapter = get_adapter("vietnamnet")
    raw = RawDocument(
        url="https://vietnamnet.vn/cong-nghe/test-123.html",
        source_id="vietnamnet",
        html="<html><body><h1>Tin công nghệ không có ngày đăng</h1><article>Nội dung AI</article></body></html>",
        text="Tin công nghệ không có ngày đăng",
    )
    parsed = await adapter.parse(raw)
    assert parsed.published_at is None


async def test_publication_date_prefers_metadata_over_deadline_in_title():
    adapter = get_adapter("baodauthau")
    sample_html = """
    <html><head>
      <meta property="article:published_time" content="2026-08-23T07:00:56+07:00">
    </head><body>
      <h1>Khẩn trương hoàn thiện 14 dự án luật trước 24/8/2026</h1>
      <article><p>Hoàn thiện hồ sơ trước ngày 24/8/2026.</p></article>
    </body></html>
    """
    raw = RawDocument(
        url="https://baodauthau.vn/test-post1.html",
        source_id="baodauthau",
        html=sample_html,
        text="Khẩn trương hoàn thiện trước 24/8/2026",
    )
    parsed = await adapter.parse(raw)
    assert parsed.published_at is not None
    assert parsed.published_at.strftime("%d/%m/%Y %H:%M") == "23/08/2026 07:00"


async def test_date_in_title_without_publication_metadata_is_not_accepted():
    adapter = get_adapter("baodauthau")
    raw = RawDocument(
        url="https://baodauthau.vn/test-post2.html",
        source_id="baodauthau",
        html="<html><body><h1>Nộp hồ sơ trước 31/12/2026</h1><article>Nội dung</article></body></html>",
        text="Nộp hồ sơ trước 31/12/2026",
    )
    parsed = await adapter.parse(raw)
    assert parsed.published_at is None

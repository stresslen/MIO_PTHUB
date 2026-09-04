import pytest
import datetime
from app.pipeline.normalize import (
    normalize_unicode,
    clean_html,
    parse_vietnamese_currency,
    parse_datetime,
    extract_location,
    extract_contact_info,
    normalize_phone_numbers,
    canonicalize_url,
)
from app.pipeline.dedup import compute_fingerprint
from app.pipeline.extract import AIAuthenticationError, prefilter_keywords, ai_extractor


def test_normalize_unicode_and_html():
    raw_html = "<div class='title'>  UBND &nbsp; Tỉnh Quảng Ninh\n\t <script>alert(1)</script></div>"
    cleaned = clean_html(raw_html)
    assert "UBND" in cleaned
    assert "Quảng Ninh" in cleaned
    assert "alert" not in cleaned
    assert "\n" not in cleaned


def test_parse_vietnamese_currency():
    # 4.5 billion VND
    val1, txt1 = parse_vietnamese_currency("Gói thầu trị giá 4,5 tỷ VNĐ phục vụ số hóa")
    assert val1 == 4_500_000_000.0
    assert "4,5 tỷ" in txt1

    # 300 million VND
    val2, txt2 = parse_vietnamese_currency("Ngân sách dự kiến 300 triệu đồng")
    assert val2 == 300_000_000.0

    # Combo 12 tỷ 500 triệu
    val3, txt3 = parse_vietnamese_currency("Tổng mức đầu tư 12 tỷ 500 triệu")
    assert val3 == 12_500_000_000.0

    # Formatted number 15.000.000.000 đ
    val4, txt4 = parse_vietnamese_currency("Giá trị 15.000.000.000 đ")
    assert val4 == 15_000_000_000.0


def test_parse_datetime():
    dt = parse_datetime("Ngày đăng: 24/08/2026 09:30")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 8
    assert dt.day == 24
    assert dt.hour == 9
    assert dt.minute == 30


def test_extract_location():
    loc1 = extract_location("Sở Thông tin và Truyền thông Hà Nội thông báo tuyển thầu")
    assert loc1 == "Hà Nội"

    loc2 = extract_location("UBND TP. Hồ Chí Minh ban hành kế hoạch số hóa hồ sơ")
    assert loc2 == "TP.HCM"

    loc3 = extract_location("Tỉnh Quảng Ninh triển khai camera giám sát thông minh")
    assert loc3 == "Quảng Ninh"


def test_extract_contact_info():
    text = "Mọi chi tiết xin liên hệ ông Nguyễn Văn A, email: contact@dauthau.gov.vn, điện thoại 0912345678."
    name, email, phone = extract_contact_info(text)
    assert email == "contact@dauthau.gov.vn"
    assert phone == "0912345678"
    assert name is not None


def test_normalize_vietnamese_phone_numbers():
    assert normalize_phone_numbers("826891248") == "0826891248"
    assert normalize_phone_numbers("+84 28 3773 1666 (ext. 2245)") == "02837731666 máy lẻ 2245"
    assert normalize_phone_numbers("0904.634.288, 024.8888.4288") == "0904634288; 02488884288"
    assert normalize_phone_numbers("#ERROR!") is None


def test_canonicalize_url():
    url = "https://baodauthau.vn/tin-tuc.html?utm_source=facebook&utm_medium=cpc#section1"
    clean = canonicalize_url(url)
    assert "utm_source" not in clean
    assert "#section1" not in clean
    assert clean == "https://baodauthau.vn/tin-tuc.html"


def test_dedup_fingerprint_uses_only_canonical_url():
    url1 = "https://baodauthau.vn/bai-1.html"
    fp1 = compute_fingerprint(url1, "Tiêu đề A", datetime.datetime(2026, 8, 24))
    fp2 = compute_fingerprint(
        url1 + "?utm_source=test",
        "Tiêu đề hoàn toàn khác",
        datetime.datetime(2027, 1, 1),
    )

    assert fp1 == fp2
    assert len(fp1) == 64


def test_extract_organization_from_structured_owner_field():
    text = "Chủ đầu tư: Trung tâm Thông tin tín dụng Quốc gia Việt Nam\nTên dự án: Hạ tầng dữ liệu"
    assert ai_extractor._extract_org_name("Gói hạ tầng CNTT", text) == "Trung tâm Thông tin tín dụng Quốc gia Việt Nam"


def test_strict_extraction_prompt_separates_publication_date_and_deadline():
    prompt = ai_extractor._extraction_prompt("Hoàn thiện trước 24/8/2026", "Ngày đăng: 23/08/2026", "baodauthau", ["hệ thống thông tin"])
    assert "KHÔNG dùng ngày đăng bài" in prompt
    assert "KEYWORD KHỚP TỪ GOOGLE SHEETS: hệ thống thông tin" in prompt
    assert "Ngày đăng do crawler lấy từ metadata riêng" in prompt
    assert '"Đang cập nhật"' in prompt


def test_round_one_rejects_website_not_present_in_source():
    data = {"organization_website": "https://invented.example.vn"}
    rejected = ai_extractor._keep_source_backed_website(data, "Bài gốc không có đường dẫn công ty")
    assert rejected["organization_website"] is None

    accepted = ai_extractor._keep_source_backed_website(
        {"organization_website": "https://abc.vn/gioi-thieu"},
        "Thông tin tham khảo tại abc.vn",
    )
    assert accepted["organization_website"] == "https://abc.vn/gioi-thieu"


def test_ai_401_is_classified_as_authentication_error(monkeypatch):
    import pytest
    from app.config import settings

    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "configured-test-key")

    def reject(*args, **kwargs):
        raise RuntimeError("Custom AI Gateway extraction error: 401")

    monkeypatch.setattr(ai_extractor, "_extract_gemini", reject)
    with pytest.raises(AIAuthenticationError):
        ai_extractor.extract("Tin AI", "Nội dung", raise_on_api_error=True)


async def test_frontend_priority_pauses_background_and_uses_reserved_executor():
    import asyncio
    import threading

    from app.services.priority_service import PriorityCoordinator

    coordinator = PriorityCoordinator()
    release_background = asyncio.Event()

    async def run_background():
        await release_background.wait()
        return await coordinator.run_blocking(
            lambda: "background", worker_name="test background"
        )

    background_task = asyncio.create_task(run_background())
    try:
        async with coordinator.fe_priority_context("test frontend"):
            release_background.set()
            await asyncio.sleep(0.02)
            assert coordinator.is_fe_active is True
            assert coordinator.is_current_task_frontend is True
            assert background_task.done() is False

            thread_name = await coordinator.run_blocking(
                lambda: threading.current_thread().name,
                worker_name="test frontend",
            )
            assert thread_name.startswith("mio-fe-priority")

        assert coordinator.is_fe_active is False
        assert await asyncio.wait_for(background_task, timeout=1) == "background"
    finally:
        coordinator._frontend_executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_frontend_preempts_inflight_background_async_operation():
    import asyncio

    from app.services.priority_service import BackgroundPreemptedError, PriorityCoordinator

    coordinator = PriorityCoordinator()
    started = asyncio.Event()

    async def slow_navigation():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        coordinator.run_async(slow_navigation, worker_name="test background navigation")
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        async with coordinator.fe_priority_context("test frontend preempt"):
            assert coordinator.is_fe_active is True
        with pytest.raises(BackgroundPreemptedError):
            await asyncio.wait_for(task, timeout=1)
        assert coordinator.is_fe_active is False
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        coordinator._frontend_executor.shutdown(wait=True)

import datetime
from app.pipeline.normalize import utc_now
from app.pipeline.scoring import scoring_engine


def test_scoring_hot_lead():
    now = utc_now()
    pub = now - datetime.timedelta(hours=12)
    deadline = now + datetime.timedelta(days=10)

    res = scoring_engine.evaluate(
        title="Gói thầu số hóa và OCR hồ sơ lưu trữ",
        need_summary="Xây dựng hệ thống nhận dạng ký tự quang học OCR và số hóa 1 triệu trang tài liệu.",
        need_categories=["OCR / Số hóa tài liệu", "Computer Vision / Thị giác máy tính"],
        budget_value=6_000_000_000.0,
        location="Hà Nội",
        contact_email="dauthau@hanoi.gov.vn",
        contact_phone="0988776655",
        deadline=deadline,
        published_at=pub,
        relevance=0.9,
    )

    assert res.total_score >= 90
    assert res.recommended_action == "CALL"
    assert len(res.reasons) >= 5
    assert any("+25" in r or "gói thầu" in r for r in res.reasons)
    assert any("Hà Nội" in r for r in res.reasons)


def test_scoring_qualified_lead():
    now = utc_now()
    pub = now - datetime.timedelta(days=1)

    res = scoring_engine.evaluate(
        title="Dự án nâng cấp hệ thống phần mềm quản lý và trợ lý ảo",
        need_summary="Triển khai Voice bot và trợ lý ảo giải đáp thủ tục hành chính.",
        need_categories=["Voice AI / Trợ lý giọng nói"],
        budget_value=3_500_000_000.0,
        location="Hà Nội",
        contact_email="sales-lead@gov.vn",
        contact_phone=None,
        deadline=None,
        published_at=pub,
        relevance=0.85,
    )

    assert 80 <= res.total_score <= 89
    assert res.recommended_action == "EMAIL"


def test_scoring_nurture_lead():
    now = utc_now()
    pub = now - datetime.timedelta(days=10)

    res = scoring_engine.evaluate(
        title="Hội nghị phổ biến kiến thức chuyển đổi số ngành nông nghiệp",
        need_summary="Định hướng kế hoạch ứng dụng công nghệ thông tin giai đoạn 2026-2030.",
        need_categories=["Chuyển đổi số / Digital Transformation"],
        budget_value=None,
        location="Tuyên Quang",
        contact_email=None,
        contact_phone=None,
        deadline=None,
        published_at=pub,
        relevance=0.35,
    )

    assert res.total_score < 80
    assert res.recommended_action == "NURTURE"


def test_scoring_expired_penalty():
    now = utc_now()
    pub = now - datetime.timedelta(days=30)
    expired_deadline = now - datetime.timedelta(days=5)

    res = scoring_engine.evaluate(
        title="Gói thầu số hóa tài liệu",
        need_summary="Gói thầu số hóa",
        need_categories=["OCR / Số hóa tài liệu"],
        budget_value=4_000_000_000.0,
        location="Hà Nội",
        contact_email="test@gov.vn",
        contact_phone=None,
        deadline=expired_deadline,
        published_at=pub,
        relevance=0.8,
    )

    assert any("-30" in r or "đã qua" in r for r in res.reasons)
    assert res.total_score < 90

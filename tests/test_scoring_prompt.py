import datetime
from pathlib import Path

from fastapi.testclient import TestClient

import app.api.scoring as scoring_api
from app.main import app
from app.services.scoring_prompt_service import (
    DEFAULT_SALES_PROMPT,
    DEFAULT_SCORING_PROMPT,
    SALES_PROMPT_SETTING_KEY,
    SCORING_PROMPT_SETTING_KEY,
    ScoringPromptService,
)


class FakeSheets:
    def __init__(self, configured=True, stored=None):
        self.configured = configured
        self.stored = stored or {}
        self.saved = []
        self.last_error = None

    def load_setting(self, key):
        return self.stored.get(key)

    def save_setting(self, key, value):
        self.saved.append((key, value))
        self.stored[key] = value
        return True


def test_default_prompts_are_seeded_separately_in_settings():
    sheets = FakeSheets()
    service = ScoringPromptService(sheets=sheets)

    scoring = service.get_config("scoring", refresh=True)
    sales = service.get_config("sales", refresh=True)

    assert scoring["prompt"] == DEFAULT_SCORING_PROMPT
    assert scoring["setting_key"] == SCORING_PROMPT_SETTING_KEY
    assert sales["prompt"] == DEFAULT_SALES_PROMPT
    assert sales["setting_key"] == SALES_PROMPT_SETTING_KEY
    assert {item[0] for item in sheets.saved} == {
        SCORING_PROMPT_SETTING_KEY,
        SALES_PROMPT_SETTING_KEY,
    }


def test_custom_prompts_are_saved_and_used_independently():
    sheets = FakeSheets()
    service = ScoringPromptService(sheets=sheets)
    scoring_custom = (
        "Chấm điểm dựa trên nhu cầu, ý định mua, ngân sách, thời hạn và chất lượng liên hệ. "
        "Chỉ dùng dữ liệu có minh chứng và tự chọn CALL, EMAIL hoặc NURTURE phù hợp."
    )
    sales_custom = (
        "Viết kịch bản Sales gồm đối tượng, cách mở đầu, thông điệp giá trị, câu hỏi khám phá "
        "và bước tiếp theo. Không bịa thông tin còn thiếu hoặc khẳng định quá mức."
    )

    scoring = service.update_prompt("scoring", scoring_custom)
    sales = service.update_prompt("sales", sales_custom)
    runtime = service.build_runtime_prompt(
        title="Gói thầu OCR",
        need_summary="Số hóa hồ sơ",
        need_categories=["OCR"],
        budget_value=2_000_000_000,
        location="Hà Nội",
        contact_email="sales@example.vn",
        contact_phone="0912345678",
        deadline=datetime.datetime(2026, 9, 1),
        published_at=datetime.datetime(2026, 8, 25),
        relevance=0.91,
        evidence=["Đơn vị mời thầu hệ thống số hóa hồ sơ."],
    )

    assert scoring["prompt"] == scoring_custom
    assert sales["prompt"] == sales_custom
    assert sheets.stored[SCORING_PROMPT_SETTING_KEY]["prompt"] == scoring_custom
    assert sheets.stored[SALES_PROMPT_SETTING_KEY]["prompt"] == sales_custom
    assert scoring_custom in runtime
    assert sales_custom in runtime
    assert "sales@example.vn" in runtime
    assert "JSON BẮT BUỘC" in runtime


def test_separate_prompt_apis(monkeypatch):
    def fake_get(prompt_type, refresh=False):
        default = DEFAULT_SCORING_PROMPT if prompt_type == "scoring" else DEFAULT_SALES_PROMPT
        key = SCORING_PROMPT_SETTING_KEY if prompt_type == "scoring" else SALES_PROMPT_SETTING_KEY
        return {
            "prompt_type": prompt_type,
            "prompt": default,
            "default_prompt": default,
            "is_default": True,
            "setting_key": key,
            "storage": "google_sheets",
        }

    def fake_update(prompt_type, prompt):
        return {**fake_get(prompt_type), "prompt": prompt, "is_default": False}

    monkeypatch.setattr(scoring_api.scoring_prompt_service, "get_config", fake_get)
    monkeypatch.setattr(scoring_api.scoring_prompt_service, "update_prompt", fake_update)
    client = TestClient(app)

    scoring_response = client.get("/api/scoring/prompts/scoring")
    sales_response = client.get("/api/scoring/prompts/sales")
    assert scoring_response.status_code == 200
    assert scoring_response.json()["setting_key"] == SCORING_PROMPT_SETTING_KEY
    assert sales_response.status_code == 200
    assert sales_response.json()["setting_key"] == SALES_PROMPT_SETTING_KEY

    custom = "A" * 120
    response = client.put("/api/scoring/prompts/sales", json={"prompt": custom})
    assert response.status_code == 200
    assert response.json()["prompt_type"] == "sales"
    assert response.json()["prompt"] == custom


def test_frontend_uses_separate_editors_and_cache_busted_javascript():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static/index.html").read_text(encoding="utf-8")
    javascript = (root / "static/js/app.js").read_text(encoding="utf-8")

    assert "Gemini + XAH Search" not in html
    assert "Dữ liệu được tổng hợp từ nguồn công khai" not in html
    assert 'id="scoring-prompt-modal"' in html
    assert 'id="sales-prompt-modal"' in html
    assert 'id="btn-open-scoring-prompt"' in html
    assert 'id="btn-open-sales-prompt"' in html
    assert "/static/js/app.js?v=2.5.0" in html
    assert "/api/scoring/prompts/" in javascript
    assert "Cơ sở chấm điểm" not in javascript
    assert "Kịch bản tiếp cận đề xuất" in javascript
    assert "createDetailItem('Email', contactEmail)" in javascript
    assert "createDetailItem('Số điện thoại', contactPhone)" in javascript
    assert "Xem nguồn gốc" in javascript

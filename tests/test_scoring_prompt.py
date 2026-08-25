import datetime
from pathlib import Path

from fastapi.testclient import TestClient

import app.api.scoring as scoring_api
from app.main import app
from app.services.scoring_prompt_service import (
    DEFAULT_SCORING_PROMPT,
    SCORING_PROMPT_SETTING_KEY,
    ScoringPromptService,
)


class FakeSheets:
    def __init__(self, configured=True, stored=None):
        self.configured = configured
        self.stored = stored
        self.saved = []
        self.last_error = None

    def load_setting(self, key):
        assert key == SCORING_PROMPT_SETTING_KEY
        return self.stored

    def save_setting(self, key, value):
        self.saved.append((key, value))
        self.stored = value
        return True


def test_default_prompt_is_seeded_in_settings():
    sheets = FakeSheets()
    service = ScoringPromptService(sheets=sheets)

    config = service.get_config(refresh=True)

    assert config["prompt"] == DEFAULT_SCORING_PROMPT
    assert config["storage"] == "google_sheets"
    assert sheets.saved[0][0] == SCORING_PROMPT_SETTING_KEY
    assert sheets.saved[0][1]["prompt"] == DEFAULT_SCORING_PROMPT


def test_custom_prompt_is_saved_and_used_in_runtime_prompt():
    sheets = FakeSheets(stored={"prompt": DEFAULT_SCORING_PROMPT})
    service = ScoringPromptService(sheets=sheets)
    custom = (
        "Hãy ưu tiên tín hiệu có nhu cầu triển khai rõ ràng và chỉ dùng dữ liệu được cung cấp. "
        "Viết kịch bản Sales gồm mở đầu, câu hỏi khám phá, thông điệp giá trị và bước tiếp theo."
    )

    config = service.update_prompt(custom)
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

    assert config["prompt"] == custom
    assert sheets.saved[-1][1]["prompt"] == custom
    assert custom in runtime
    assert "sales@example.vn" in runtime
    assert "Đơn vị mời thầu hệ thống số hóa hồ sơ." in runtime
    assert "JSON BẮT BUỘC" in runtime


def test_scoring_prompt_api(monkeypatch):
    expected = {
        "prompt": DEFAULT_SCORING_PROMPT,
        "default_prompt": DEFAULT_SCORING_PROMPT,
        "is_default": True,
        "storage": "google_sheets",
    }
    monkeypatch.setattr(
        scoring_api.scoring_prompt_service,
        "get_config",
        lambda refresh=False: expected,
    )
    monkeypatch.setattr(
        scoring_api.scoring_prompt_service,
        "update_prompt",
        lambda prompt: {**expected, "prompt": prompt, "is_default": False},
    )
    client = TestClient(app)

    response = client.get("/api/scoring/prompt")
    assert response.status_code == 200
    assert response.json()["storage"] == "google_sheets"

    custom = "A" * 120
    response = client.put("/api/scoring/prompt", json={"prompt": custom})
    assert response.status_code == 200
    assert response.json()["prompt"] == custom


def test_frontend_removes_score_basis_and_exposes_prompt_editor():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static/index.html").read_text(encoding="utf-8")
    javascript = (root / "static/js/app.js").read_text(encoding="utf-8")

    assert "Gemini + XAH Search" not in html
    assert "Dữ liệu được tổng hợp từ nguồn công khai" not in html
    assert 'id="scoring-prompt-modal"' in html
    assert "Cơ sở chấm điểm" not in javascript
    assert "Kịch bản tiếp cận đề xuất" in javascript
    assert "createDetailItem('Email', contactEmail)" in javascript
    assert "createDetailItem('Số điện thoại', contactPhone)" in javascript

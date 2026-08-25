from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services.keyword_service import (
    KeywordService,
    KeywordValidationError,
    MAX_DISCOVERY_KEYWORDS,
    parse_keyword_input,
)


class FakeKeywordSheets:
    configured = True

    def __init__(self):
        self.rows = []

    def seed_keyword_rows(self, rows):
        if self.rows:
            return 0
        self.rows = [dict(row) for row in rows]
        return len(self.rows)

    def get_keyword_rows(self):
        return [dict(row) for row in self.rows]

    def upsert_keyword_rows(self, rows):
        indexed = {row["keyword"].casefold(): row for row in self.rows}
        added = promoted = duplicates = 0
        for incoming in rows:
            key = incoming["keyword"].casefold()
            existing = indexed.get(key)
            if existing is None:
                copied = dict(incoming)
                self.rows.append(copied)
                indexed[key] = copied
                added += 1
            elif incoming["use_for_discovery"] and not existing["use_for_discovery"]:
                existing["use_for_discovery"] = True
                promoted += 1
            else:
                duplicates += 1
        return {"added": added, "promoted": promoted, "duplicates": duplicates}


def test_parse_keyword_input_supports_all_requested_formats_and_deduplicates():
    content = "  Chuyển đổi số, camera AI; OCR\ntrung tâm dữ liệu\r\nCAMERA AI  "
    assert parse_keyword_input(content) == [
        "Chuyển đổi số",
        "camera AI",
        "OCR",
        "trung tâm dữ liệu",
    ]


def test_bootstrap_moves_yaml_keywords_to_sheet_and_builds_runtime_cache():
    sheets = FakeKeywordSheets()
    service = KeywordService(sheets)

    state = service.bootstrap()
    config = service.get_config()

    assert state["source"] == "google_sheets"
    assert state["total"] > 50
    assert state["discovery_total"] == 6
    assert len(sheets.rows) == state["total"]
    assert "group_a_technology" in config["keyword_groups"]
    assert config["discovery_search"]["keywords"] == [
        "chuyển đổi số",
        "trí tuệ nhân tạo",
        "số hóa",
        "công nghệ thông tin",
        "phần mềm",
        "cơ sở dữ liệu",
    ]


def test_add_appends_new_keywords_skips_duplicates_and_refreshes_cache():
    sheets = FakeKeywordSheets()
    service = KeywordService(sheets)
    service.bootstrap()

    result = service.add("camera AI; quản lý tài sản, camera ai\nERP mới")

    assert result["added"] == 2
    assert result["duplicates"] == 1
    assert service.snapshot()["total"] == len(sheets.rows)
    assert "quản lý tài sản" in service.get_config()["keyword_groups"]["custom"]["keywords"]


def test_discovery_import_has_a_hard_request_budget():
    sheets = FakeKeywordSheets()
    service = KeywordService(sheets)
    service.bootstrap()
    values = [f"search keyword {index}" for index in range(MAX_DISCOVERY_KEYWORDS)]

    with pytest.raises(KeywordValidationError, match="tối đa"):
        service.add("\n".join(values), use_for_discovery=True)


def test_keywords_api_exposes_cache_and_validates_import(monkeypatch):
    from app.api import keywords as keywords_api

    monkeypatch.setattr(
        keywords_api.keyword_service,
        "add",
        lambda content, use_for_discovery=False: {
            "added": 2,
            "promoted": 0,
            "duplicates": 1,
            "submitted": 3,
            "total": 90,
        },
    )
    client = TestClient(app)

    listed = client.get("/api/keywords")
    imported = client.post(
        "/api/keywords/import",
        json={"content": "a,b,a", "use_for_discovery": False},
    )

    assert listed.status_code == 200
    assert "items" in listed.json()
    assert imported.status_code == 200
    assert imported.json()["added"] == 2

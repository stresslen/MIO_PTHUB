from __future__ import annotations

import base64
import csv
import datetime
import io
import json
import logging
from typing import Any

from app.config import settings
from app.pipeline.normalize import normalize_phone_numbers

logger = logging.getLogger(__name__)

LEAD_HEADERS = [
    "id", "source", "source_url", "title", "published_at", "crawled_at",
    "organization_name", "organization_type", "need_summary", "need_categories",
    "budget_value", "budget_text", "location", "contact_name", "contact_email",
    "contact_phone", "deadline", "keywords_matched", "relevance", "score",
    "recommended_action", "score_reasons", "evidence", "sales_strategy",
    "content_fingerprint", "status", "sales_notes", "updated_at",
]
SETTINGS_HEADERS = ["key", "value", "updated_at"]
JSON_FIELDS = {"need_categories", "keywords_matched", "score_reasons", "evidence"}
DATE_FIELDS = {"published_at", "crawled_at", "deadline", "updated_at"}


class GoogleSheetsService:
    """Google Sheets is the durable store; SQLite remains a local query cache."""

    def __init__(self) -> None:
        self._spreadsheet = None
        self._text_formatted_worksheets: set[int] = set()
        self.last_error: str | None = None

    @property
    def configured(self) -> bool:
        """Whether authenticated read/write access is configured."""
        return bool(settings.google_sheets_spreadsheet_id and settings.google_service_account_json)

    @property
    def read_configured(self) -> bool:
        """A spreadsheet ID is enough for public CSV read fallback."""
        return bool(settings.google_sheets_spreadsheet_id)

    def _credentials_info(self) -> dict[str, Any]:
        raw = (settings.google_service_account_json or "").strip()
        if not raw:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON chưa được cấu hình")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                return json.loads(base64.b64decode(raw).decode("utf-8"))
            except Exception as exc:
                raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON không phải JSON hoặc base64 JSON hợp lệ") from exc

    def connect(self):
        if self._spreadsheet is not None:
            return self._spreadsheet
        if not self.configured:
            return None
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            credentials = Credentials.from_service_account_info(
                self._credentials_info(),
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            self._spreadsheet = gspread.authorize(credentials).open_by_key(
                settings.google_sheets_spreadsheet_id
            )
            self.last_error = None
            return self._spreadsheet
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Không thể kết nối Google Sheets: %s", exc)
            raise

    def _worksheet(self, title: str, headers: list[str]):
        spreadsheet = self.connect()
        if spreadsheet is None:
            return None
        if title.startswith("gid:"):
            try:
                worksheet = spreadsheet.get_worksheet_by_id(int(title.removeprefix("gid:")))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Worksheet ID không hợp lệ: {title}") from exc
            if worksheet is None:
                raise RuntimeError(f"Không tìm thấy worksheet {title}")
        else:
            try:
                worksheet = spreadsheet.worksheet(title)
            except Exception:
                worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(20, len(headers)))
        first_row = worksheet.row_values(1)
        if "raw_content_ref" in first_row and "raw_content_ref" not in headers:
            worksheet.delete_columns(first_row.index("raw_content_ref") + 1)
            first_row = worksheet.row_values(1)
        if first_row != headers:
            worksheet.update(values=[headers], range_name="A1")
        if headers == LEAD_HEADERS and worksheet.id not in self._text_formatted_worksheets:
            worksheet.format("P2:P", {"numberFormat": {"type": "TEXT"}})
            self._text_formatted_worksheets.add(worksheet.id)
        return worksheet

    def _lead_row(self, lead: Any) -> list[Any]:
        return [
            self._cell_value(
                normalize_phone_numbers(getattr(lead, name, None))
                if name == "contact_phone"
                else getattr(lead, name, None)
            )
            for name in LEAD_HEADERS
        ]

    @staticmethod
    def _cell_value(value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        if hasattr(value, "value"):
            return value.value
        return value

    def upsert_lead(self, lead: Any) -> bool:
        if not self.configured:
            return False
        try:
            worksheet = self._worksheet(settings.google_sheets_leads_worksheet, LEAD_HEADERS)
            row = self._lead_row(lead)
            ids = worksheet.col_values(1)
            try:
                row_number = ids.index(str(lead.id)) + 1
                worksheet.update(values=[row], range_name=f"A{row_number}")
            except ValueError:
                worksheet.append_row(row, value_input_option="RAW")
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Đồng bộ lead lên Google Sheets thất bại: %s", exc)
            return False

    def sync_sqlite(self, db: Any) -> int:
        """Append every SQLite lead missing from the configured worksheet.

        This is intentionally non-destructive: rows already present in Sheets are
        retained, while updates created by the application continue through
        ``upsert_lead``.
        """
        if not self.configured:
            return 0
        from app.models.lead import Lead

        try:
            worksheet = self._worksheet(settings.google_sheets_leads_worksheet, LEAD_HEADERS)
            existing_ids = {
                str(value).strip()
                for value in worksheet.col_values(1)[1:]
                if str(value).strip()
            }
            leads = db.query(Lead).order_by(Lead.crawled_at.asc()).all()
            missing_rows = [
                self._lead_row(lead)
                for lead in leads
                if str(lead.id) not in existing_ids
            ]
            if missing_rows:
                worksheet.append_rows(missing_rows, value_input_option="RAW")
            self.last_error = None
            return len(missing_rows)
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Chuyển dữ liệu SQLite lên Google Sheets thất bại: %s", exc)
            raise

    def _public_records(self) -> list[dict[str, Any]]:
        """Read a publicly shared worksheet without exposing credentials."""
        import requests

        worksheet_name = settings.google_sheets_leads_worksheet
        params: dict[str, str] = {"format": "csv"}
        if worksheet_name.startswith("gid:"):
            params["gid"] = worksheet_name.removeprefix("gid:")
        else:
            params["sheet"] = worksheet_name
        url = (
            "https://docs.google.com/spreadsheets/d/"
            f"{settings.google_sheets_spreadsheet_id}/export"
        )
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
        if reader.fieldnames != LEAD_HEADERS:
            raise RuntimeError("Header Google Sheet không khớp schema Lead")
        return list(reader)

    def hydrate_sqlite(self, db: Any) -> int:
        if not self.read_configured:
            return 0
        from app.models.lead import Lead

        try:
            if self.configured:
                worksheet = self._worksheet(settings.google_sheets_leads_worksheet, LEAD_HEADERS)
                records = worksheet.get_all_records(expected_headers=LEAD_HEADERS)
            else:
                records = self._public_records()
            imported = 0
            for record in records:
                fingerprint = str(record.get("content_fingerprint") or "").strip()
                if not fingerprint or db.query(Lead).filter(Lead.content_fingerprint == fingerprint).first():
                    continue
                values: dict[str, Any] = {}
                for field in LEAD_HEADERS:
                    value = record.get(field)
                    if value in (None, ""):
                        values[field] = None if field not in JSON_FIELDS else []
                    elif field in JSON_FIELDS:
                        try:
                            values[field] = json.loads(value) if isinstance(value, str) else value
                        except json.JSONDecodeError:
                            values[field] = []
                    elif field in DATE_FIELDS:
                        try:
                            values[field] = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
                        except ValueError:
                            values[field] = None
                    elif field in {"score"}:
                        values[field] = int(float(value))
                    elif field in {"budget_value", "relevance"}:
                        values[field] = float(value)
                    elif field == "contact_phone":
                        values[field] = normalize_phone_numbers(value)
                    else:
                        values[field] = value
                if not values.get("id"):
                    values.pop("id", None)
                values["source"] = values.get("source") or "google_sheets"
                values["source_url"] = values.get("source_url") or ""
                values["title"] = values.get("title") or "Không có tiêu đề"
                values["status"] = values.get("status") or "NEW"
                values["recommended_action"] = values.get("recommended_action") or "NURTURE"
                values["crawled_at"] = values.get("crawled_at") or datetime.datetime.utcnow()
                db.add(Lead(**values))
                imported += 1
            db.commit()
            self.last_error = None
            return imported
        except Exception as exc:
            db.rollback()
            self.last_error = str(exc)
            logger.error("Nạp dữ liệu từ Google Sheets thất bại: %s", exc)
            return 0

    def save_setting(self, key: str, value: dict[str, Any]) -> bool:
        if not self.configured:
            return False
        try:
            worksheet = self._worksheet(settings.google_sheets_settings_worksheet, SETTINGS_HEADERS)
            keys = worksheet.col_values(1)
            row = [key, json.dumps(value, ensure_ascii=False), datetime.datetime.now(datetime.timezone.utc).isoformat()]
            try:
                row_number = keys.index(key) + 1
                worksheet.update(values=[row], range_name=f"A{row_number}")
            except ValueError:
                worksheet.append_row(row, value_input_option="RAW")
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Lưu setting lên Google Sheets thất bại: %s", exc)
            return False

    def load_setting(self, key: str) -> dict[str, Any] | None:
        if not self.configured:
            return None
        try:
            worksheet = self._worksheet(settings.google_sheets_settings_worksheet, SETTINGS_HEADERS)
            for record in worksheet.get_all_records(expected_headers=SETTINGS_HEADERS):
                if record.get("key") == key:
                    return json.loads(record.get("value") or "{}")
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Đọc setting từ Google Sheets thất bại: %s", exc)
        return None

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "connected": self._spreadsheet is not None and self.last_error is None,
            "spreadsheet_id": settings.google_sheets_spreadsheet_id[-6:] if settings.google_sheets_spreadsheet_id else None,
            "last_error": self.last_error,
            "role": "durable_store" if self.configured else "not_configured",
        }


google_sheets_service = GoogleSheetsService()

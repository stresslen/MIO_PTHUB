from __future__ import annotations

import base64
import csv
import datetime
import io
import json
import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def _normalize_phone(value: Any) -> str:
    """Import lazily so Google Sheets scripts do not trigger a pipeline import cycle."""
    from app.pipeline.normalize import normalize_phone_numbers as normalize

    return normalize(value)


LEAD_HEADERS = [
    "id", "source", "source_url", "title", "published_at", "crawled_at",
    "organization_name", "organization_type", "need_summary", "need_categories",
    "budget_value", "budget_text", "location", "contact_name", "contact_email",
    "contact_phone", "deadline", "keywords_matched", "relevance", "score",
    "recommended_action", "score_reasons", "evidence", "sales_strategy",
    "content_fingerprint", "status", "sales_notes", "updated_at",
    "organization_id", "enrichment_status", "enrichment_message",
]
SETTINGS_HEADERS = ["key", "value", "updated_at"]
KEYWORD_HEADERS = [
    "keyword", "group_id", "group_name", "use_for_filter",
    "use_for_discovery", "active", "created_at", "updated_at",
]
SOURCE_HEADERS = [
    "id", "name", "description", "seed_urls", "adapter_mode", "adapter_key",
    "crawl_scope", "rate_limit_delay", "timeout", "enabled",
    "include_in_schedule", "status", "last_error",
    "last_attempt_at", "last_success_at", "created_at", "updated_at",
]

ORGANIZATION_HEADERS = [
    "id", "legal_name", "aliases", "official_url", "domain", "tax_code",
    "organization_type", "industry", "size", "locations", "revenue",
    "employee_count", "technologies", "profile_status", "missing_information",
    "verification_confidence", "xah_used", "source_urls", "error_message",
    "verified_at", "updated_at",
]
CONTACT_HEADERS = [
    "id", "organization_id", "full_name", "raw_title", "role_group", "email",
    "phone", "profile_url", "source_url", "evidence_text", "decision_score",
    "decision_reason", "verified_at",
]
EVIDENCE_HEADERS = [
    "id", "organization_id", "field", "value", "source_url", "evidence_text",
    "crawled_at", "confidence",
]
COLLECTION_HEADERS = [
    "id", "organization_id", "title", "summary", "published_at", "source_url",
    "payload", "updated_at",
]
INTERACTION_HEADERS = [
    "id", "organization_id", "occurred_at", "owner", "contact_name", "channel",
    "content", "result", "next_action", "updated_at",
]
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
        import gspread
        from google.oauth2.service_account import Credentials

        credentials = Credentials.from_service_account_info(
            self._credentials_info(),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        for attempt in range(1, 4):
            try:
                self._spreadsheet = gspread.authorize(credentials).open_by_key(
                    settings.google_sheets_spreadsheet_id
                )
                self.last_error = None
                return self._spreadsheet
            except Exception as exc:
                self._spreadsheet = None
                self.last_error = str(exc)
                if attempt == 3:
                    logger.error("Không thể kết nối Google Sheets sau 3 lần: %s", exc)
                    raise
                logger.warning(
                    "Google Sheets tạm lỗi, thử lại lần %s/3: %s",
                    attempt + 1,
                    exc,
                )
                time.sleep(attempt)
        return None

    @staticmethod
    def _is_ai_processed(item: Any) -> bool:
        getter = (
            item.get
            if isinstance(item, dict)
            else lambda key, default=None: getattr(item, key, default)
        )
        status = str(getter("status", "") or "").upper()
        organization = str(getter("organization_name", "") or "").strip().lower()
        summary = str(getter("need_summary", "") or "").strip().lower()
        try:
            score = float(getter("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        return bool(
            status != "PENDING_AI"
            and organization not in {"", "đang chờ ai bóc tách", "đang cập nhật"}
            and not summary.startswith("[hàng đợi ai]")
            and score >= 40
        )

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
        elif headers == CONTACT_HEADERS and worksheet.id not in self._text_formatted_worksheets:
            worksheet.format("G2:G", {"numberFormat": {"type": "TEXT"}})
            self._text_formatted_worksheets.add(worksheet.id)
        return worksheet

    def _lead_row(self, lead: Any) -> list[Any]:
        return [
            self._cell_value(
                _normalize_phone(getattr(lead, name, None))
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
        if not self.configured or not self._is_ai_processed(lead):
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
                if str(lead.id) not in existing_ids and self._is_ai_processed(lead)
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
                if not self._is_ai_processed(record):
                    continue
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
                        values[field] = _normalize_phone(value)
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

    @staticmethod
    def _json_value(value: Any, default: Any) -> Any:
        if value in (None, ""):
            return default
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(str(value))
        except (TypeError, json.JSONDecodeError):
            return default

    @staticmethod
    def _date_value(value: Any) -> datetime.datetime | None:
        if value in (None, ""):
            return None
        try:
            return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def hydrate_profiles_sqlite(self, db: Any) -> dict[str, int]:
        """Restore round-two entities from Sheets into Render's ephemeral SQLite cache."""
        counts = {"organizations": 0, "contacts": 0, "evidence": 0, "collections": 0}
        if not self.configured:
            return counts
        from app.models.organization import Organization, OrganizationContact, OrganizationEvidence

        try:
            org_records = self._worksheet(
                settings.google_sheets_organizations_worksheet, ORGANIZATION_HEADERS
            ).get_all_records(expected_headers=ORGANIZATION_HEADERS)
            for record in org_records:
                org_id = str(record.get("id") or "").strip()
                legal_name = str(record.get("legal_name") or "").strip()
                if not org_id or not legal_name:
                    continue
                organization = db.query(Organization).filter(Organization.id == org_id).first()
                if organization is None:
                    organization = Organization(id=org_id, legal_name=legal_name)
                    db.add(organization)
                    counts["organizations"] += 1
                organization.legal_name = legal_name
                for field in ("official_url", "domain", "tax_code", "organization_type", "industry", "size",
                              "employee_count", "profile_status", "error_message"):
                    setattr(organization, field, record.get(field) or None)
                for field in ("aliases", "locations", "technologies", "missing_information", "source_urls"):
                    setattr(organization, field, self._json_value(record.get(field), []))
                organization.revenue = self._json_value(record.get("revenue"), None)
                try:
                    organization.verification_confidence = float(record.get("verification_confidence") or 0.0)
                except (TypeError, ValueError):
                    organization.verification_confidence = 0.0
                organization.xah_used = 1 if str(record.get("xah_used") or "").lower() in {"1", "true", "yes"} else 0
                organization.verified_at = self._date_value(record.get("verified_at"))
                organization.updated_at = self._date_value(record.get("updated_at"))
            db.flush()

            contact_records = self._worksheet(
                settings.google_sheets_contacts_worksheet, CONTACT_HEADERS
            ).get_all_records(expected_headers=CONTACT_HEADERS)
            for record in contact_records:
                item_id = str(record.get("id") or "").strip()
                organization_id = str(record.get("organization_id") or "").strip()
                if not item_id or not organization_id or db.query(Organization).filter(Organization.id == organization_id).first() is None:
                    continue
                item = db.query(OrganizationContact).filter(OrganizationContact.id == item_id).first()
                if item is None:
                    item = OrganizationContact(id=item_id, organization_id=organization_id,
                                               source_url=str(record.get("source_url") or ""))
                    db.add(item)
                    counts["contacts"] += 1
                for field in ("full_name", "raw_title", "role_group", "email", "profile_url",
                              "source_url", "evidence_text", "decision_reason"):
                    setattr(item, field, record.get(field) or None)
                item.phone = _normalize_phone(record.get("phone"))
                try:
                    item.decision_score = int(float(record["decision_score"])) if record.get("decision_score") not in (None, "") else None
                except (TypeError, ValueError):
                    item.decision_score = None
                item.verified_at = self._date_value(record.get("verified_at"))

            evidence_records = self._worksheet(
                settings.google_sheets_evidence_worksheet, EVIDENCE_HEADERS
            ).get_all_records(expected_headers=EVIDENCE_HEADERS)
            for record in evidence_records:
                item_id = str(record.get("id") or "").strip()
                organization_id = str(record.get("organization_id") or "").strip()
                if not item_id or not organization_id or not record.get("field") or not record.get("source_url"):
                    continue
                if db.query(Organization).filter(Organization.id == organization_id).first() is None:
                    continue
                item = db.query(OrganizationEvidence).filter(OrganizationEvidence.id == item_id).first()
                if item is None:
                    item = OrganizationEvidence(
                        id=item_id, organization_id=organization_id,
                        field=str(record["field"]), source_url=str(record["source_url"]),
                        evidence_text=str(record.get("evidence_text") or ""),
                    )
                    db.add(item)
                    counts["evidence"] += 1
                item.value = self._json_value(record.get("value"), record.get("value"))
                item.evidence_text = str(record.get("evidence_text") or "")
                item.crawled_at = self._date_value(record.get("crawled_at")) or datetime.datetime.utcnow()
                try:
                    item.confidence = float(record.get("confidence") or 0.0)
                except (TypeError, ValueError):
                    item.confidence = 0.0

            collection_specs = [
                (settings.google_sheets_projects_worksheet, "projects"),
                (settings.google_sheets_news_worksheet, "news"),
                (settings.google_sheets_jobs_worksheet, "jobs"),
                (settings.google_sheets_tenders_worksheet, "tenders"),
            ]
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for worksheet_name, field in collection_specs:
                records = self._worksheet(worksheet_name, COLLECTION_HEADERS).get_all_records(
                    expected_headers=COLLECTION_HEADERS
                )
                for record in records:
                    organization_id = str(record.get("organization_id") or "").strip()
                    if not organization_id:
                        continue
                    payload = self._json_value(record.get("payload"), {})
                    if not isinstance(payload, dict) or not payload:
                        payload = {
                            "title": record.get("title"), "summary": record.get("summary"),
                            "published_at": record.get("published_at"), "source_url": record.get("source_url"),
                        }
                    grouped.setdefault((organization_id, field), []).append(payload)
                    counts["collections"] += 1
            for (organization_id, field), values in grouped.items():
                organization = db.query(Organization).filter(Organization.id == organization_id).first()
                if organization is not None:
                    setattr(organization, field, values)
            db.commit()
            self.last_error = None
            return counts
        except Exception as exc:
            db.rollback()
            self.last_error = str(exc)
            logger.error("Nạp Company Profile từ Google Sheets thất bại: %s", exc)
            return counts

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

    @staticmethod
    def _keyword_row(item: dict[str, Any]) -> list[Any]:
        return [GoogleSheetsService._cell_value(item.get(name)) for name in KEYWORD_HEADERS]

    def get_keyword_rows(self) -> list[dict[str, Any]]:
        """Return keyword records from the dedicated worksheet."""
        if not self.configured:
            raise RuntimeError("Google Sheets chưa được cấu hình để quản lý keyword")
        worksheet = self._worksheet(settings.google_sheets_keywords_worksheet, KEYWORD_HEADERS)
        return worksheet.get_all_records(expected_headers=KEYWORD_HEADERS)

    def seed_keyword_rows(self, rows: list[dict[str, Any]]) -> int:
        """Populate a new/empty Keywords worksheet without overwriting user data."""
        if not self.configured:
            return 0
        worksheet = self._worksheet(settings.google_sheets_keywords_worksheet, KEYWORD_HEADERS)
        existing = [str(value).strip() for value in worksheet.col_values(1)[1:] if str(value).strip()]
        if existing:
            return 0
        values = [self._keyword_row(item) for item in rows]
        if values:
            worksheet.append_rows(values, value_input_option="RAW")
        self.last_error = None
        return len(values)

    def upsert_keyword_rows(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        """Append new keywords and promote existing rows without creating duplicates."""
        if not self.configured:
            raise RuntimeError("Google Sheets chưa được cấu hình để quản lý keyword")
        worksheet = self._worksheet(settings.google_sheets_keywords_worksheet, KEYWORD_HEADERS)
        records = worksheet.get_all_records(expected_headers=KEYWORD_HEADERS)
        indexed = {
            str(record.get("keyword") or "").strip().casefold(): (position + 2, record)
            for position, record in enumerate(records)
            if str(record.get("keyword") or "").strip()
        }
        added = promoted = duplicates = 0
        additions: list[list[Any]] = []
        for item in rows:
            key = str(item.get("keyword") or "").strip().casefold()
            if not key:
                continue
            existing = indexed.get(key)
            if existing is None:
                additions.append(self._keyword_row(item))
                indexed[key] = (-1, item)
                added += 1
                continue
            row_number, record = existing
            wants_discovery = bool(item.get("use_for_discovery"))
            has_discovery = str(record.get("use_for_discovery") or "").strip().lower() in {
                "true", "1", "yes", "y", "có",
            }
            if row_number > 0 and wants_discovery and not has_discovery:
                merged = dict(record)
                merged.update(
                    use_for_filter=True,
                    use_for_discovery=True,
                    active=True,
                    updated_at=item.get("updated_at"),
                )
                worksheet.update(values=[self._keyword_row(merged)], range_name=f"A{row_number}")
                indexed[key] = (row_number, merged)
                promoted += 1
            else:
                duplicates += 1
        if additions:
            worksheet.append_rows(additions, value_input_option="RAW")
        self.last_error = None
        return {"added": added, "promoted": promoted, "duplicates": duplicates}

    @staticmethod
    def _source_row(item: dict[str, Any]) -> list[Any]:
        values = dict(item)
        values["seed_urls"] = json.dumps(values.get("seed_urls") or [], ensure_ascii=False)
        return [GoogleSheetsService._cell_value(values.get(name)) for name in SOURCE_HEADERS]

    def get_source_rows(self) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("Google Sheets chưa được cấu hình để quản lý nguồn")
        worksheet = self._worksheet(settings.google_sheets_sources_worksheet, SOURCE_HEADERS)
        return worksheet.get_all_records(expected_headers=SOURCE_HEADERS)

    def seed_source_rows(self, rows: list[dict[str, Any]]) -> int:
        """Seed Sources once and never overwrite rows managed by the user."""
        if not self.configured:
            return 0
        worksheet = self._worksheet(settings.google_sheets_sources_worksheet, SOURCE_HEADERS)
        existing = [str(value).strip() for value in worksheet.col_values(1)[1:] if str(value).strip()]
        if existing:
            return 0
        values = [self._source_row(item) for item in rows]
        if values:
            worksheet.append_rows(values, value_input_option="RAW")
        self.last_error = None
        return len(values)

    def upsert_source_row(self, item: dict[str, Any]) -> bool:
        if not self.configured:
            raise RuntimeError("Google Sheets chưa được cấu hình để quản lý nguồn")
        worksheet = self._worksheet(settings.google_sheets_sources_worksheet, SOURCE_HEADERS)
        row = self._source_row(item)
        ids = worksheet.col_values(1)
        try:
            row_number = ids.index(str(item["id"])) + 1
            worksheet.update(values=[row], range_name=f"A{row_number}")
        except ValueError:
            worksheet.append_row(row, value_input_option="RAW")
        self.last_error = None
        return True

    @staticmethod
    def _model_row(item: Any, headers: list[str]) -> list[Any]:
        return [GoogleSheetsService._cell_value(getattr(item, name, None)) for name in headers]

    @staticmethod
    def _dict_row(item: dict[str, Any], headers: list[str]) -> list[Any]:
        return [GoogleSheetsService._cell_value(item.get(name)) for name in headers]

    @staticmethod
    def _upsert_row(worksheet: Any, row_id: str, row: list[Any]) -> None:
        ids = worksheet.col_values(1)
        try:
            row_number = ids.index(str(row_id)) + 1
            worksheet.update(values=[row], range_name=f"A{row_number}")
        except ValueError:
            worksheet.append_row(row, value_input_option="RAW")

    @staticmethod
    def _collection_id(organization_id: str, kind: str, item: dict[str, Any]) -> str:
        import hashlib
        raw = "|".join([
            organization_id, kind, str(item.get("source_url") or ""),
            str(item.get("name") or item.get("title") or ""),
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:36]

    def upsert_organization_profile(self, organization_id: str) -> bool:
        """Write verified round-two entities into dedicated Google Sheets tabs."""
        if not self.configured or not organization_id:
            return False
        from app.database import SessionLocal
        from app.models.organization import Organization, OrganizationContact, OrganizationEvidence

        db = SessionLocal()
        try:
            organization = db.query(Organization).filter(Organization.id == organization_id).first()
            if organization is None:
                return False
            org_ws = self._worksheet(settings.google_sheets_organizations_worksheet, ORGANIZATION_HEADERS)
            self._upsert_row(org_ws, organization.id, self._model_row(organization, ORGANIZATION_HEADERS))

            contact_ws = self._worksheet(settings.google_sheets_contacts_worksheet, CONTACT_HEADERS)
            contacts = db.query(OrganizationContact).filter(
                OrganizationContact.organization_id == organization.id
            ).all()
            for contact in contacts:
                self._upsert_row(contact_ws, contact.id, self._model_row(contact, CONTACT_HEADERS))

            evidence_ws = self._worksheet(settings.google_sheets_evidence_worksheet, EVIDENCE_HEADERS)
            evidence = db.query(OrganizationEvidence).filter(
                OrganizationEvidence.organization_id == organization.id
            ).all()
            for item in evidence:
                self._upsert_row(evidence_ws, item.id, self._model_row(item, EVIDENCE_HEADERS))

            collections = [
                (settings.google_sheets_projects_worksheet, "projects", organization.projects or []),
                (settings.google_sheets_news_worksheet, "news", organization.news or []),
                (settings.google_sheets_jobs_worksheet, "jobs", organization.jobs or []),
                (settings.google_sheets_tenders_worksheet, "tenders", organization.tenders or []),
            ]
            for worksheet_name, kind, values in collections:
                worksheet = self._worksheet(worksheet_name, COLLECTION_HEADERS)
                for value in values:
                    if not isinstance(value, dict):
                        continue
                    row_id = self._collection_id(organization.id, kind, value)
                    row = {
                        "id": row_id,
                        "organization_id": organization.id,
                        "title": value.get("name") or value.get("title"),
                        "summary": value.get("summary"),
                        "published_at": value.get("published_at"),
                        "source_url": value.get("source_url"),
                        "payload": value,
                        "updated_at": organization.updated_at,
                    }
                    self._upsert_row(worksheet, row_id, self._dict_row(row, COLLECTION_HEADERS))

            # Interactions is reserved for user/CRM data and is never fabricated by crawling.
            self._worksheet(settings.google_sheets_interactions_worksheet, INTERACTION_HEADERS)
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Đồng bộ Company Profile lên Google Sheets thất bại: %s", exc)
            return False
        finally:
            db.close()

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "connected": self._spreadsheet is not None and self.last_error is None,
            "spreadsheet_id": settings.google_sheets_spreadsheet_id[-6:] if settings.google_sheets_spreadsheet_id else None,
            "keywords_worksheet": settings.google_sheets_keywords_worksheet,
            "sources_worksheet": settings.google_sheets_sources_worksheet,
            "last_error": self.last_error,
            "role": "durable_store" if self.configured else "not_configured",
        }


google_sheets_service = GoogleSheetsService()

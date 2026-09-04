from __future__ import annotations

import datetime
import json
import logging
from typing import Any
from app.database import SessionLocal
from app.models.setting import SystemSetting

logger = logging.getLogger(__name__)


class SettingService:
    """SQLite-backed persistent key-value configuration service."""

    @staticmethod
    def load_setting(key: str) -> dict[str, Any]:
        """Load setting dictionary by key from SQLite."""
        session = SessionLocal()
        try:
            row = session.query(SystemSetting).filter_by(key=key).first()
            if row and row.value is not None:
                if isinstance(row.value, dict):
                    return row.value
                if isinstance(row.value, str):
                    try:
                        parsed = json.loads(row.value)
                        return parsed if isinstance(parsed, dict) else {"value": parsed}
                    except json.JSONDecodeError:
                        return {"value": row.value}
                return {"value": row.value}
            return {}
        except Exception:
            logger.exception("Lỗi đọc setting '%s' từ SQLite", key)
            return {}
        finally:
            session.close()

    @staticmethod
    def save_setting(key: str, value: Any) -> None:
        """Upsert setting by key in SQLite."""
        session = SessionLocal()
        try:
            val_to_save = value if isinstance(value, (dict, list)) else {"value": value}
            row = session.query(SystemSetting).filter_by(key=key).first()
            now = datetime.datetime.utcnow()
            if row is not None:
                row.value = val_to_save
                row.updated_at = now
            else:
                row = SystemSetting(key=key, value=val_to_save, updated_at=now)
                session.add(row)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Lỗi lưu setting '%s' vào SQLite", key)
            raise
        finally:
            session.close()


setting_service = SettingService()

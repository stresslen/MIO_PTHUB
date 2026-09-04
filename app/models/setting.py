from __future__ import annotations

import datetime
from sqlalchemy import Column, DateTime, JSON, String
from app.database import Base


class SystemSetting(Base):
    """General key-value configuration table backed by SQLite."""

    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True, index=True)
    value = Column(JSON, nullable=False, default=dict)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

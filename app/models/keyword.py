from __future__ import annotations

import datetime
from sqlalchemy import Boolean, Column, DateTime, String
from app.database import Base


class KeywordItem(Base):
    """Keyword table backed by SQLite."""

    __tablename__ = "keywords"

    keyword = Column(String(250), primary_key=True, index=True)
    group_id = Column(String(100), nullable=False, default="custom")
    group_name = Column(String(200), nullable=False, default="Custom Keywords")
    use_for_filter = Column(Boolean, nullable=False, default=True)
    use_for_discovery = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

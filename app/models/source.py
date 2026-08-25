from __future__ import annotations

import datetime
import uuid
from enum import Enum
from typing import Literal, Optional, List
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
)
from pydantic import BaseModel, Field
from app.database import Base


class CrawlStatusEnum(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


# ==========================================
# SQLAlchemy DB Model: CrawlRun
# ==========================================
class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default=CrawlStatusEnum.PENDING.value, index=True)
    start_time = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)

    total_discovered = Column(Integer, default=0)
    new_leads = Column(Integer, default=0)
    duplicate_leads = Column(Integer, default=0)
    filtered_out = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)


# ==========================================
# Pydantic Schemas
# ==========================================
class CrawlRunRead(BaseModel):
    id: str
    source: str
    status: CrawlStatusEnum
    start_time: datetime.datetime
    end_time: Optional[datetime.datetime] = None
    total_discovered: int
    new_leads: int
    duplicate_leads: int
    filtered_out: int
    error_count: int
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class SourceInfo(BaseModel):
    id: str
    name: str
    base_url: str
    seed_urls: List[str] = Field(default_factory=list)
    type: str
    adapter_mode: str = "specialized"
    enabled: bool
    include_in_schedule: bool = True
    priority: str
    description: str
    status: str = "READY"
    last_error: Optional[str] = None
    last_crawl_at: Optional[datetime.datetime] = None
    last_status: Optional[str] = None
    total_leads_count: int = 0
    hot_leads_count: int = 0


class SourceImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    include_in_schedule: bool = False


class TriggerCrawlRequest(BaseModel):
    source_id: Optional[str] = None  # None means run all enabled sources
    force_recrawl: bool = False
    timeframe: Literal["1_day", "1_week", "1_month"] = "1_week"

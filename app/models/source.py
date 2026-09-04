from __future__ import annotations

import datetime
import uuid
from enum import Enum
from typing import Literal, Optional, List
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
)
from pydantic import BaseModel, Field
from app.database import Base


class CrawlStatusEnum(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    INTERRUPTED = "INTERRUPTED"
    PAUSED = "PAUSED"


class CrawlJobStatusEnum(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


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


class CrawlJob(Base):
    """Durable hand-off between the FE/API process and the crawl worker."""

    __tablename__ = "crawl_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String(100), nullable=True, index=True)
    trigger = Column(String(20), nullable=False, default="FE", index=True)
    status = Column(
        String(20), nullable=False, default=CrawlJobStatusEnum.QUEUED.value, index=True
    )
    timeframe = Column(String(20), nullable=False, default="1_week")
    force_recrawl = Column(Boolean, nullable=False, default=False)
    requested_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    worker_id = Column(String(120), nullable=True)
    result_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    dedupe_key = Column(String(160), nullable=True, unique=True)


class SchedulerState(Base):
    """Cross-process scheduler configuration, heartbeat and latest result."""

    __tablename__ = "scheduler_state"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    timezone = Column(String(64), nullable=False, default="Asia/Ho_Chi_Minh")
    hour = Column(Integer, nullable=False, default=6)
    minute = Column(Integer, nullable=False, default=0)
    next_run_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    total_automated_runs = Column(Integer, nullable=False, default=0)
    last_run_summary_json = Column(Text, nullable=True)
    worker_heartbeat_at = Column(DateTime, nullable=True)
    config_updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    config_dirty = Column(Boolean, nullable=False, default=False)
    persistent_config_loaded = Column(Boolean, nullable=False, default=False)


class CrawlerSourceItem(Base):
    """Crawler source configuration and status table backed by SQLite."""

    __tablename__ = "crawler_sources"

    id = Column(String(100), primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True, default="")
    seed_urls = Column(JSON, nullable=False, default=list)
    adapter_mode = Column(String(50), nullable=False, default="specialized")
    adapter_key = Column(String(100), nullable=False, default="")
    crawl_scope = Column(String(50), nullable=False, default="configured")
    rate_limit_delay = Column(Float, nullable=False, default=1.0)
    timeout = Column(Integer, nullable=False, default=30)
    enabled = Column(Boolean, nullable=False, default=True)
    include_in_schedule = Column(Boolean, nullable=False, default=True)
    status = Column(String(30), nullable=False, default="READY")
    last_error = Column(Text, nullable=True, default="")
    last_attempt_at = Column(String(50), nullable=True, default="")
    last_success_at = Column(String(50), nullable=True, default="")
    created_at = Column(String(50), nullable=True, default="")
    updated_at = Column(String(50), nullable=True, default="")


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


class CrawlJobRead(BaseModel):
    id: str
    source_id: Optional[str] = None
    trigger: str
    status: CrawlJobStatusEnum
    timeframe: str
    force_recrawl: bool
    requested_at: datetime.datetime
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    result: Optional[dict] = None
    error_message: Optional[str] = None


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

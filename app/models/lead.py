from __future__ import annotations

import datetime
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Integer,
    DateTime,
    JSON,
    Index,
)
from pydantic import BaseModel, Field
from app.database import Base
from app.models.organization import OrganizationProfileRead


class ActionEnum(str, Enum):
    CALL = "CALL"
    EMAIL = "EMAIL"
    NURTURE = "NURTURE"


class LeadStatusEnum(str, Enum):
    NEW = "NEW"
    PENDING_AI = "PENDING_AI"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    DISMISSED = "DISMISSED"
    ARCHIVED = "ARCHIVED"


class OrganizationTypeEnum(str, Enum):
    GOVERNMENT = "government"
    ENTERPRISE = "enterprise"
    OTHER = "other"


# ==========================================
# SQLAlchemy DB Model
# ==========================================
class Lead(Base):
    __tablename__ = "leads"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(50), nullable=False, index=True)
    source_url = Column(String(1000), nullable=False)
    title = Column(String(500), nullable=False)
    published_at = Column(DateTime, nullable=True, index=True)
    crawled_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

    organization_name = Column(String(300), nullable=True, index=True)
    organization_type = Column(String(50), default="other")
    need_summary = Column(Text, nullable=True)
    need_categories = Column(JSON, default=list)  # List[str]

    budget_value = Column(Float, nullable=True, index=True)  # Normalized in VND
    budget_text = Column(String(200), nullable=True)
    location = Column(String(150), nullable=True, index=True)

    contact_name = Column(String(200), nullable=True)
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(100), nullable=True)

    deadline = Column(DateTime, nullable=True, index=True)
    keywords_matched = Column(JSON, default=list)  # List[str]

    relevance = Column(Float, default=0.0)  # 0.0 to 1.0
    score = Column(Integer, default=0, index=True)  # 0 to 100
    recommended_action = Column(String(20), default="NURTURE", index=True)  # CALL, EMAIL, NURTURE
    score_reasons = Column(JSON, default=list)  # List[str]
    evidence = Column(JSON, default=list)  # List[str] snippets

    raw_content_ref = Column(String(500), nullable=True)
    content_fingerprint = Column(String(64), unique=True, nullable=False, index=True)

    sales_strategy = Column(Text, nullable=True)  # AI generated sales strategy & angle
    status = Column(String(30), default="NEW", index=True)  # NEW, CONTACTED, QUALIFIED, DISMISSED
    sales_notes = Column(Text, nullable=True)
    organization_id = Column(String(36), nullable=True, index=True)
    enrichment_status = Column(String(50), nullable=True, index=True)
    enrichment_message = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        Index("idx_leads_score_action", "score", "recommended_action"),
        Index("idx_leads_source_published", "source", "published_at"),
    )


# ==========================================
# Pydantic Schemas
# ==========================================
class ContactInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class LeadBase(BaseModel):
    source: str
    source_url: str
    title: str
    published_at: Optional[datetime.datetime] = None
    organization_name: Optional[str] = None
    organization_type: Optional[str] = "other"
    need_summary: Optional[str] = None
    need_categories: List[str] = Field(default_factory=list)
    budget_value: Optional[float] = None
    budget_text: Optional[str] = None
    location: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    deadline: Optional[datetime.datetime] = None
    keywords_matched: List[str] = Field(default_factory=list)
    relevance: float = 0.0
    score: int = 0
    recommended_action: ActionEnum = ActionEnum.NURTURE
    score_reasons: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    sales_strategy: Optional[str] = None
    content_fingerprint: str
    organization_id: Optional[str] = None
    enrichment_status: Optional[str] = None
    enrichment_message: Optional[str] = None


class LeadCreate(LeadBase):
    pass


class LeadRead(LeadBase):
    id: str
    crawled_at: datetime.datetime
    status: LeadStatusEnum
    sales_notes: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class LeadDetailRead(LeadRead):
    company_profile: Optional["OrganizationProfileRead"] = None


class LeadStatusUpdate(BaseModel):
    status: LeadStatusEnum
    sales_notes: Optional[str] = None


class LeadFilterParams(BaseModel):
    source: Optional[str] = None
    action: Optional[ActionEnum] = None
    status: Optional[LeadStatusEnum] = None
    min_score: Optional[int] = None
    max_score: Optional[int] = None
    category: Optional[str] = None
    location: Optional[str] = None
    query: Optional[str] = None
    include_archived: bool = False  # False means only show score >= 40 on dashboard
    page: int = 1
    page_size: int = 20
    sort_by: str = "score"  # score, crawled_at, published_at, budget_value
    sort_order: str = "desc"  # asc, desc

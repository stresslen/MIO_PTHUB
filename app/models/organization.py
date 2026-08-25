from __future__ import annotations

import datetime
import uuid
from typing import Any, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, Index

from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    legal_name = Column(String(300), nullable=False, index=True)
    aliases = Column(JSON, default=list)
    official_url = Column(String(1000), nullable=True)
    domain = Column(String(255), nullable=True, index=True)
    tax_code = Column(String(50), nullable=True, index=True)
    organization_type = Column(String(50), nullable=True)
    industry = Column(String(300), nullable=True)
    size = Column(String(200), nullable=True)
    locations = Column(JSON, default=list)
    revenue = Column(JSON, nullable=True)
    employee_count = Column(String(100), nullable=True)
    technologies = Column(JSON, default=list)
    projects = Column(JSON, default=list)
    news = Column(JSON, default=list)
    jobs = Column(JSON, default=list)
    tenders = Column(JSON, default=list)
    profile_status = Column(String(50), nullable=False, default="PROFILE_INCOMPLETE", index=True)
    missing_information = Column(JSON, default=list)
    verification_confidence = Column(Float, default=0.0)
    xah_used = Column(Integer, default=0)
    source_urls = Column(JSON, default=list)
    error_message = Column(Text, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        Index("idx_organizations_domain_tax", "domain", "tax_code"),
    )


class OrganizationContact(Base):
    __tablename__ = "organization_contacts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    full_name = Column(String(250), nullable=True)
    raw_title = Column(String(300), nullable=True)
    role_group = Column(String(80), nullable=True)
    email = Column(String(250), nullable=True)
    phone = Column(String(100), nullable=True)
    profile_url = Column(String(1000), nullable=True)
    source_url = Column(String(1000), nullable=False)
    evidence_text = Column(Text, nullable=True)
    decision_score = Column(Integer, nullable=True)
    decision_reason = Column(Text, nullable=True)
    verified_at = Column(DateTime, nullable=True)


class OrganizationEvidence(Base):
    __tablename__ = "organization_evidence"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    field = Column(String(100), nullable=False, index=True)
    value = Column(JSON, nullable=True)
    source_url = Column(String(1000), nullable=False)
    evidence_text = Column(Text, nullable=False)
    crawled_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    confidence = Column(Float, default=0.0)


class ContactProfile(BaseModel):
    id: Optional[str] = None
    full_name: Optional[str] = None
    raw_title: Optional[str] = None
    role_group: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    profile_url: Optional[str] = None
    source_url: str
    evidence_text: Optional[str] = None
    decision_score: Optional[int] = None
    decision_reason: Optional[str] = None
    verified_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class EvidenceProfile(BaseModel):
    id: Optional[str] = None
    field: str
    value: Any = None
    source_url: str
    evidence_text: str
    crawled_at: Optional[datetime.datetime] = None
    confidence: float = 0.0

    class Config:
        from_attributes = True


class OrganizationProfileRead(BaseModel):
    id: str
    legal_name: str
    aliases: List[str] = Field(default_factory=list)
    official_url: Optional[str] = None
    domain: Optional[str] = None
    tax_code: Optional[str] = None
    organization_type: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    locations: List[Any] = Field(default_factory=list)
    revenue: Any = None
    employee_count: Optional[str] = None
    technologies: List[Any] = Field(default_factory=list)
    projects: List[Any] = Field(default_factory=list)
    news: List[Any] = Field(default_factory=list)
    jobs: List[Any] = Field(default_factory=list)
    tenders: List[Any] = Field(default_factory=list)
    profile_status: str
    missing_information: List[str] = Field(default_factory=list)
    verification_confidence: float = 0.0
    xah_used: bool = False
    source_urls: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    verified_at: Optional[datetime.datetime] = None
    contacts: List[ContactProfile] = Field(default_factory=list)
    evidence: List[EvidenceProfile] = Field(default_factory=list)

    class Config:
        from_attributes = True

from __future__ import annotations

from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class ScoreBreakdownItem(BaseModel):
    rule_name: str
    points: int
    reason: str


class ScoreResult(BaseModel):
    total_score: int
    recommended_action: str  # CALL, EMAIL, NURTURE
    reasons: List[str]
    breakdown: List[ScoreBreakdownItem] = Field(default_factory=list)
    sales_strategy_suggestion: Optional[str] = None
    evaluated_by: str = "ai_gemini"  # configured AI provider identifier


class AIExtractionResult(BaseModel):
    organization_name: Optional[str] = None
    organization_type: str = "government"
    need_summary: Optional[str] = None
    need_categories: List[str] = Field(default_factory=list)
    budget_value: Optional[float] = None
    budget_text: Optional[str] = None
    location: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    deadline: Optional[str] = None  # ISO format string
    relevance: float = 0.0
    evidence: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    web_search_used: bool = False
    search_sources: List[str] = Field(default_factory=list)

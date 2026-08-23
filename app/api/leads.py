from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import (
    LeadRead,
    LeadStatusUpdate,
    LeadFilterParams,
    ActionEnum,
    LeadStatusEnum,
)
from app.services.lead_service import lead_service
from app.services.google_sheets_service import google_sheets_service

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("", response_model=Dict[str, Any])
def get_leads(
    source: Optional[str] = Query(None, description="Filter by source ID"),
    action: Optional[ActionEnum] = Query(None, description="Filter by CALL/EMAIL/NURTURE"),
    status: Optional[LeadStatusEnum] = Query(None, description="Filter by Lead status"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum score"),
    max_score: Optional[int] = Query(None, ge=0, le=100, description="Maximum score"),
    location: Optional[str] = Query(None, description="Filter by location (e.g. Hà Nội)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    query: Optional[str] = Query(None, description="Search term in title, need, or org"),
    include_archived: bool = Query(False, description="Include low score/archived leads (<40)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("score", description="Sort field: score, crawled_at, published_at, budget_value"),
    sort_order: str = Query("desc", description="Sort direction: asc or desc"),
    db: Session = Depends(get_db),
):
    """
    List and filter leads with multi-criteria search, pagination, and sorting.
    """
    params = LeadFilterParams(
        source=source,
        action=action,
        status=status,
        min_score=min_score,
        max_score=max_score,
        location=location,
        category=category,
        query=query,
        include_archived=include_archived,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    leads, total = lead_service.get_leads(db, params)
    
    return {
        "items": [LeadRead.model_validate(lead) for lead in leads],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/{lead_id}", response_model=LeadRead)
def get_lead_detail(lead_id: str, db: Session = Depends(get_db)):
    """Retrieve detailed information, evidence, and score reasons for a lead."""
    lead = lead_service.get_lead_by_id(db, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadRead.model_validate(lead)


@router.patch("/{lead_id}/status", response_model=LeadRead)
def update_lead_status(
    lead_id: str,
    payload: LeadStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update sales workflow status and notes for a lead."""
    updated = lead_service.update_lead_status(db, lead_id, payload.status, payload.sales_notes)
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found")
    google_sheets_service.upsert_lead(updated)
    return LeadRead.model_validate(updated)

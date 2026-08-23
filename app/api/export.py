from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import LeadFilterParams, ActionEnum, LeadStatusEnum
from app.services.lead_service import lead_service
from app.services.export_service import export_service

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/csv")
def export_leads_csv(
    source: Optional[str] = Query(None),
    action: Optional[ActionEnum] = Query(None),
    status: Optional[LeadStatusEnum] = Query(None),
    min_score: Optional[int] = Query(None),
    max_score: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Export filtered leads to CSV format with UTF-8-BOM encoding for Excel."""
    params = LeadFilterParams(
        source=source,
        action=action,
        status=status,
        min_score=min_score,
        max_score=max_score,
        page=1,
        page_size=10000,  # export all filtered
    )
    leads, _ = lead_service.get_leads(db, params)
    csv_content = export_service.export_to_csv(leads)

    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=AI_Leads_Intelligence.csv",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/json")
def export_leads_json(
    source: Optional[str] = Query(None),
    action: Optional[ActionEnum] = Query(None),
    db: Session = Depends(get_db),
):
    """Export filtered leads to JSON format."""
    params = LeadFilterParams(
        source=source,
        action=action,
        page=1,
        page_size=10000,
    )
    leads, _ = lead_service.get_leads(db, params)
    json_content = export_service.export_to_json(leads)

    return Response(
        content=json_content,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=AI_Leads_Intelligence.json",
            "X-Content-Type-Options": "nosniff",
        },
    )

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.lead_service import lead_service

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("", response_model=Dict[str, Any])
def get_dashboard_statistics(db: Session = Depends(get_db)):
    """Retrieve aggregate KPI statistics for the Executive & Sales Dashboard."""
    return lead_service.get_dashboard_stats(db)

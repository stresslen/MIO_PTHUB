from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_sources_config
from app.database import get_db
from app.models.lead import Lead
from app.models.source import SourceInfo, CrawlRun

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get("", response_model=List[SourceInfo])
def get_sources(db: Session = Depends(get_db)):
    """List configured data sources and their health metrics."""
    sources_cfg = get_sources_config().get("sources", [])
    results: List[SourceInfo] = []

    for src in sources_cfg:
        src_id = src.get("id")
        
        # Get lead count
        total_leads = db.query(func.count(Lead.id)).filter(Lead.source == src_id).scalar() or 0
        hot_leads = db.query(func.count(Lead.id)).filter(Lead.source == src_id, Lead.recommended_action == "CALL").scalar() or 0

        # Get last crawl run
        last_run = (
            db.query(CrawlRun)
            .filter(CrawlRun.source == src_id)
            .order_by(CrawlRun.start_time.desc())
            .first()
        )

        results.append(
            SourceInfo(
                id=src_id,
                name=src.get("name", src_id),
                base_url=(src.get("base_url") or (src.get("seed_urls") or [""])[0]),
                type=src.get("type", "html"),
                enabled=src.get("enabled", True),
                priority=src.get("priority", "P0"),
                description=src.get("description", ""),
                last_crawl_at=last_run.start_time if last_run else None,
                last_status=last_run.status if last_run else "NEVER_RUN",
                total_leads_count=total_leads,
                hot_leads_count=hot_leads,
            )
        )

    return results

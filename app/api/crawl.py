from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.source import (
    CrawlRun,
    CrawlRunRead,
    TriggerCrawlRequest,
)
from app.services.crawler_service import crawler_service

router = APIRouter(prefix="/crawl", tags=["Crawl"])


@router.post("/run", response_model=List[CrawlRunRead])
async def trigger_crawl(
    request: TriggerCrawlRequest,
    background_tasks: BackgroundTasks,
    sync: bool = Query(True, description="Run synchronously for immediate demo results"),
    db: Session = Depends(get_db),
):
    """
    Trigger live crawler manually for a specific source or all sources.
    Processes live data from target portals end-to-end.
    """
    if request.source_id:
        if sync:
            run_res = await crawler_service.run_crawler_for_source(
                source_id=request.source_id,
                db=db,
                force_recrawl=request.force_recrawl,
                max_items=request.max_items,
                timeframe=request.timeframe,
                is_manual_fe=True,
            )
            return [CrawlRunRead.model_validate(run_res)]
        else:
            # Run with FE High Priority
            background_tasks.add_task(
                crawler_service.run_crawler_for_source,
                request.source_id,
                None,
                request.force_recrawl,
                request.max_items,
                request.timeframe,
                True,  # is_manual_fe
            )
            return []
    else:
        # Run all sources
        if sync:
            runs = await crawler_service.run_all_sources(
                force_recrawl=request.force_recrawl,
                max_items=request.max_items,
                timeframe=request.timeframe,
                is_manual_fe=True,
            )
            return [CrawlRunRead.model_validate(r) for r in runs]
        else:
            background_tasks.add_task(
                crawler_service.run_all_sources,
                request.force_recrawl,
                request.max_items,
                request.timeframe,
                25,    # batch_size
                True,  # is_manual_fe
            )
            return []

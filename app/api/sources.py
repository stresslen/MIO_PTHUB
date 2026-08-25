from __future__ import annotations

import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import Lead
from app.models.source import SourceImportRequest, SourceInfo, CrawlRun
from app.services.source_service import source_service
from app.services.linkedin_settings_service import linkedin_settings_service

router = APIRouter(prefix="/sources", tags=["Sources"])


class LinkedInConfigUpdate(BaseModel):
    max_posts_per_keyword: int = Field(ge=1, le=1000)


@router.get("", response_model=List[SourceInfo])
def get_sources(db: Session = Depends(get_db)):
    """List sources from the Google Sheets-backed runtime registry."""
    results: List[SourceInfo] = []
    for src in source_service.snapshot()["items"]:
        src_id = src["id"]
        total_leads = db.query(func.count(Lead.id)).filter(Lead.source == src_id).scalar() or 0
        hot_leads = db.query(func.count(Lead.id)).filter(
            Lead.source == src_id,
            Lead.recommended_action == "CALL",
        ).scalar() or 0
        last_run = (
            db.query(CrawlRun)
            .filter(CrawlRun.source == src_id)
            .order_by(CrawlRun.start_time.desc())
            .first()
        )
        results.append(SourceInfo(
            id=src_id,
            name=src["name"],
            base_url=src["seed_urls"][0],
            seed_urls=src["seed_urls"],
            type="html",
            adapter_mode=src["adapter_mode"],
            enabled=src["enabled"],
            include_in_schedule=src["include_in_schedule"],
            priority="P0" if src["adapter_mode"] == "specialized" else "CUSTOM",
            description=src["description"],
            status=src["status"],
            last_error=src["last_error"] or None,
            last_crawl_at=last_run.start_time if last_run else None,
            last_status=src["status"],
            total_leads_count=total_leads,
            hot_leads_count=hot_leads,
        ))
    return results


@router.get("/linkedin/config")
def get_linkedin_config():
    return linkedin_settings_service.get_config(refresh=True)


@router.put("/linkedin/config")
def update_linkedin_config(payload: LinkedInConfigUpdate):
    try:
        return linkedin_settings_service.update(payload.max_posts_per_keyword)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/import")
async def import_sources(payload: SourceImportRequest):
    try:
        result = await asyncio.to_thread(
            source_service.add_url,
            payload.name,
            payload.url,
            payload.include_in_schedule,
        )
        updated = []
        needs_update = 0
        for item in result["items"]:
            if item["status"] == "NEW":
                item = await asyncio.to_thread(source_service.probe, item["id"])
            if item["status"] == "NEEDS_ADAPTER":
                needs_update += 1
            updated.append(item)
        result["items"] = updated
        result["needs_update"] = needs_update
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Không thể lưu nguồn vào Google Sheets") from exc


@router.post("/refresh")
def refresh_sources():
    try:
        return source_service.refresh()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Không thể đọc worksheet Sources") from exc


@router.post("/{source_id}/probe")
async def probe_source(source_id: str):
    try:
        return await asyncio.to_thread(source_service.probe, source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy nguồn") from exc

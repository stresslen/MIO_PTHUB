from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


class ToggleSchedulerRequest(BaseModel):
    enabled: Optional[bool] = None


class SchedulerConfigRequest(BaseModel):
    enabled: bool = True
    hour: int = Field(default=6, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


@router.get("/status")
def get_scheduler_status() -> Dict[str, Any]:
    return scheduler_service.get_status()


@router.put("/config")
async def configure_scheduler(req: SchedulerConfigRequest) -> Dict[str, Any]:
    config = {
        "enabled": req.enabled,
        "hour": req.hour,
        "minute": req.minute,
    }
    return {"success": True, "status": scheduler_service.configure(config)}


@router.post("/toggle")
async def toggle_scheduler(req: ToggleSchedulerRequest) -> Dict[str, Any]:
    enabled = scheduler_service.toggle(req.enabled)
    return {"success": True, "enabled": enabled, "status": scheduler_service.get_status()}

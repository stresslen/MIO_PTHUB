from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.google_sheets_service import google_sheets_service

router = APIRouter(prefix="/storage", tags=["Storage"])


@router.get("/status")
def storage_status() -> dict[str, Any]:
    """Return safe Google Sheets configuration/connection status; never returns credentials."""
    return google_sheets_service.status()

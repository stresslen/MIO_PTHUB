from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.database import SessionLocal
from app.models.lead import Lead
from app.models.organization import Organization
from app.services.google_sheets_service import google_sheets_service

router = APIRouter(prefix="/storage", tags=["Storage"])


@router.get("/status")
def storage_status() -> dict[str, Any]:
    """Return safe storage configuration status (SQLite primary durable database)."""
    db_path = Path("leads.db").resolve()
    leads_count = 0
    orgs_count = 0
    try:
        session = SessionLocal()
        leads_count = session.query(Lead).count()
        orgs_count = session.query(Organization).count()
        session.close()
    except Exception:
        pass

    sqlite_info = {
        "type": "sqlite",
        "durable_master": True,
        "database_file": str(db_path),
        "exists": db_path.exists(),
        "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "total_leads": leads_count,
        "total_organizations": orgs_count,
        "wal_mode": True,
    }
    sheets_info = google_sheets_service.status()
    return {
        "primary": "sqlite",
        "sqlite": sqlite_info,
        "google_sheets": sheets_info,
        # Keep top-level keys for backward compatibility
        **sheets_info,
        "role": "sqlite_primary_durable",
    }

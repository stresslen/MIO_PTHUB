from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.keyword_service import KeywordValidationError, keyword_service

router = APIRouter(prefix="/keywords", tags=["keywords"])


class KeywordImportRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1_000_000)
    use_for_discovery: bool = False


@router.get("")
def list_keywords():
    return keyword_service.snapshot()


@router.post("/import")
def import_keywords(payload: KeywordImportRequest):
    try:
        return keyword_service.add(payload.content, payload.use_for_discovery)
    except KeywordValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không thể cập nhật Google Sheets: {exc}") from exc


@router.post("/refresh")
def refresh_keywords():
    try:
        return keyword_service.refresh()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không thể đọc Google Sheets: {exc}") from exc

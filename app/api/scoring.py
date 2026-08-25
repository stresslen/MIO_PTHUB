from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.scoring_prompt_service import scoring_prompt_service


router = APIRouter(prefix="/scoring", tags=["Scoring"])


class ScoringPromptUpdate(BaseModel):
    prompt: str = Field(min_length=100, max_length=30_000)


@router.get("/prompt")
def get_scoring_prompt():
    return scoring_prompt_service.get_config(refresh=True)


@router.put("/prompt")
def update_scoring_prompt(payload: ScoringPromptUpdate):
    try:
        return scoring_prompt_service.update_prompt(payload.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

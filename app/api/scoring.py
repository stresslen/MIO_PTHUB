from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.scoring_prompt_service import scoring_prompt_service


router = APIRouter(prefix="/scoring", tags=["Scoring"])
PromptType = Literal["scoring", "sales"]


class PromptUpdate(BaseModel):
    prompt: str = Field(min_length=100, max_length=30_000)


@router.get("/prompts/{prompt_type}")
def get_prompt(prompt_type: PromptType):
    return scoring_prompt_service.get_config(prompt_type, refresh=True)


@router.put("/prompts/{prompt_type}")
def update_prompt(prompt_type: PromptType, payload: PromptUpdate):
    try:
        return scoring_prompt_service.update_prompt(prompt_type, payload.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/prompt")
def get_legacy_scoring_prompt():
    return scoring_prompt_service.get_config("scoring", refresh=True)


@router.put("/prompt")
def update_legacy_scoring_prompt(payload: PromptUpdate):
    try:
        return scoring_prompt_service.update_prompt("scoring", payload.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

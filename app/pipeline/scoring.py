import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional
import requests

from app.config import settings
from app.models.scoring_rule import ScoreResult, ScoreBreakdownItem
from app.pipeline.extract import AIAuthenticationError, AIQuotaOrAPIError
from app.services.scoring_prompt_service import scoring_prompt_service

logger = logging.getLogger(__name__)


class AIScoringEngine:
    """
    AI-Powered Lead Scoring Engine.
    Uses Google Gemini (e.g. gemini-2.0-flash-lite / gemini-1.5-flash) to evaluate
    and score B2B/B2G leads across comprehensive multi-dimensional criteria.
    AI scoring is mandatory. Invalid or unavailable AI responses are surfaced to
    the crawler so an item is skipped instead of receiving a synthetic score.
    """

    def __init__(self):
        pass

    def reload_config(self):
        pass

    def evaluate(
        self,
        title: str,
        need_summary: Optional[str],
        need_categories: List[str],
        budget_value: Optional[float],
        location: Optional[str],
        contact_email: Optional[str],
        contact_phone: Optional[str],
        deadline: Optional[datetime.datetime],
        published_at: Optional[datetime.datetime],
        relevance: float = 0.0,
        raw_evidence: Optional[List[str]] = None,
    ) -> ScoreResult:
        """Evaluate a lead using only the configured AI provider.

        A failed or malformed AI response raises AIQuotaOrAPIError. The crawler
        catches it and does not persist the unfinished item.
        """
        common = {
            "title": title,
            "need_summary": need_summary,
            "need_categories": need_categories,
            "budget_value": budget_value,
            "location": location,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "deadline": deadline,
            "published_at": published_at,
            "relevance": relevance,
        }

        if settings.ai_provider == "gemini":
            if not settings.gemini_api_key:
                raise AIAuthenticationError("Chưa cấu hình GEMINI_API_KEY cho AI scoring")
            try:
                result = self._evaluate_with_gemini(
                    **common,
                    evidence=raw_evidence or [],
                )
            except (AIAuthenticationError, AIQuotaOrAPIError):
                raise
            except Exception as exc:
                raise AIQuotaOrAPIError(
                    f"Gemini scoring trả dữ liệu không hợp lệ: {exc}"
                ) from exc
            if result is None:
                raise AIQuotaOrAPIError("Gemini scoring không trả về kết quả hợp lệ")
            return result

        raise AIAuthenticationError(
            "Chấm điểm và tạo kịch bản Sales chỉ hỗ trợ AI_PROVIDER=gemini"
        )

    def _evaluate_with_gemini(
        self,
        title: str,
        need_summary: Optional[str],
        need_categories: List[str],
        budget_value: Optional[float],
        location: Optional[str],
        contact_email: Optional[str],
        contact_phone: Optional[str],
        deadline: Optional[datetime.datetime],
        published_at: Optional[datetime.datetime],
        relevance: float,
        evidence: List[str],
    ) -> Optional[ScoreResult]:
        """
        Invoke Google Gemini API (supports both direct Google AI Studio and OpenAI-compatible proxy endpoints).
        """
        prompt = scoring_prompt_service.build_runtime_prompt(
            title=title,
            need_summary=need_summary,
            need_categories=need_categories,
            budget_value=budget_value,
            location=location,
            contact_email=contact_email,
            contact_phone=contact_phone,
            deadline=deadline,
            published_at=published_at,
            relevance=relevance,
            evidence=evidence,
        )

        base_url = settings.gemini_base_url or settings.ai_base_url

        # Check if using OpenAI-compatible custom gateway / proxy (e.g. xah.io, LiteLLM, OpenRouter)
        if base_url or settings.gemini_api_key.startswith("sk-"):
            if base_url:
                api_endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url.rstrip('/')}/chat/completions"
            else:
                api_endpoint = "https://api.openai.com/v1/chat/completions"

            headers = {
                "Authorization": f"Bearer {settings.gemini_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.gemini_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            }
            resp = requests.post(api_endpoint, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Strip ```json ... ``` markdown if present
                clean_content = content.strip()
                if clean_content.startswith("```"):
                    clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content, flags=re.IGNORECASE)
                    clean_content = re.sub(r"\s*```$", "", clean_content)
                
                json_match = re.search(r"\{.*\}", clean_content, re.DOTALL)
                if json_match:
                    clean_content = json_match.group(0)

                parsed = json.loads(clean_content)
                return self._parse_ai_response(parsed)
            if resp.status_code in (401, 403):
                raise AIAuthenticationError(
                    f"Custom AI Gateway từ chối GEMINI_API_KEY (HTTP {resp.status_code})"
                )
            raise AIQuotaOrAPIError(
                f"Custom AI Gateway scoring lỗi HTTP {resp.status_code}: {resp.text[:200]}"
            )

        # Standard Google AI Studio API call
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        try:
            resp = requests.post(endpoint, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text_out = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    parsed = json.loads(text_out)
                    return self._parse_ai_response(parsed)
            elif resp.status_code in (429, 503):
                from app.pipeline.extract import AIQuotaOrAPIError
                raise AIQuotaOrAPIError(f"Gemini Scoring API quota error: {resp.status_code}")
            else:
                logger.warning(f"Google AI Studio returned status {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as req_err:
            if "429" in str(req_err) or "quota" in str(req_err).lower():
                from app.pipeline.extract import AIQuotaOrAPIError
                raise AIQuotaOrAPIError(f"Gemini API rate limit: {req_err}")
            logger.warning(f"Google AI Studio connection failed: {req_err}")

        logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text[:200]}")
        return None

    def _parse_ai_response(self, parsed: Dict[str, Any]) -> ScoreResult:
        """Helper to sanitize and build ScoreResult from AI output."""
        score = max(0, min(100, int(parsed.get("total_score", 0))))
        action = str(parsed.get("recommended_action") or "").strip().upper()
        if action not in {"CALL", "EMAIL", "NURTURE"}:
            raise ValueError("Gemini trả recommended_action không hợp lệ")

        reasons = parsed.get("score_reasons", [])
        breakdown = [
            ScoreBreakdownItem(
                rule_name=b.get("rule_name", "rule"),
                points=int(b.get("points", 0)),
                reason=b.get("reason", ""),
            )
            for b in parsed.get("breakdown", [])
        ]

        return ScoreResult(
            total_score=score,
            recommended_action=action,
            reasons=reasons,
            breakdown=breakdown,
            sales_strategy_suggestion=parsed.get("sales_strategy_suggestion"),
            evaluated_by=f"ai_{settings.gemini_model}",
        )



scoring_engine = AIScoringEngine()

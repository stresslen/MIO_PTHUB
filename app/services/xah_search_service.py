from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class XAHSearchError(RuntimeError):
    pass


class XAHSearchService:
    """Internal XAH client used by Gemini when extraction needs more facts."""

    def search(self, query: str) -> dict[str, Any]:
        if not settings.xah_api_key:
            raise XAHSearchError("Chưa cấu hình XAH_API_KEY trên backend")
        payload = {
            "model": settings.xah_search_model,
            "query": query,
            "search_type": settings.xah_search_type,
            "max_results": settings.xah_max_results,
            "country": settings.xah_country,
            "language": settings.xah_language,
        }
        response = requests.post(
            settings.xah_search_url,
            headers={
                "Authorization": f"Bearer {settings.xah_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.xah_timeout_seconds,
        )
        if not response.ok:
            raise XAHSearchError(
                f"XAH Search trả về HTTP {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        answer_obj = data.get("answer") or {}
        results: list[dict[str, Any]] = []
        for position, item in enumerate(data.get("results") or [], start=1):
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            results.append({
                "position": position,
                "title": str(item.get("title") or "").strip() or urlparse(url).netloc or url,
                "url": url,
                "snippet": str(item.get("snippet") or item.get("content") or "").strip(),
                "published_at": item.get("published_at"),
            })
        return {
            "query": data.get("query") or query,
            "answer": answer_obj.get("text") if isinstance(answer_obj, dict) else str(answer_obj),
            "results": results[: settings.xah_max_results],
            "provider": data.get("provider") or answer_obj.get("source") or "xah",
        }

    @staticmethod
    def to_gemini_context(search_data: dict[str, Any]) -> str:
        lines = ["TÓM TẮT TỪ XAH SEARCH:", search_data.get("answer") or "(không có)", "", "NGUỒN:"]
        for index, item in enumerate(search_data.get("results") or [], start=1):
            lines.extend([
                f"[XAH {index}] {item.get('title') or item.get('url')}",
                f"URL: {item.get('url')}",
                f"Đoạn trích: {item.get('snippet') or '(không có đoạn trích)' }",
            ])
        return "\n".join(lines)


xah_search_service = XAHSearchService()

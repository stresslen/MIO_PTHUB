from __future__ import annotations

import logging
import re
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
        raw_data = response.json()
        data = raw_data if isinstance(raw_data, dict) else {"results": raw_data}
        answer_obj = data.get("answer") or ""
        answer_text = self._answer_text(answer_obj)
        raw_results = self._result_items(data.get("results"))
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for item in raw_results:
            url = self._extract_url(item)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            item_dict = item if isinstance(item, dict) else {}
            results.append({
                "position": len(results) + 1,
                "title": self._first_text(item_dict, ("title", "name", "label"))
                or urlparse(url).netloc
                or url,
                "url": url,
                "snippet": self._first_text(item_dict, ("snippet", "content", "description", "summary")),
                "published_at": item_dict.get("published_at") or item_dict.get("date"),
            })

        # Some gateway responses put markdown links in ``answer`` instead of
        # returning a structured ``results`` array. Keep those URLs as a
        # fallback so the backend crawl can still continue.
        for url in self._extract_urls_from_text(answer_text):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({
                "position": len(results) + 1,
                "title": urlparse(url).netloc or url,
                "url": url,
                "snippet": answer_text,
                "published_at": None,
            })

        provider = data.get("provider")
        if not provider and isinstance(answer_obj, dict):
            provider = answer_obj.get("source") or answer_obj.get("provider")
        return {
            "query": data.get("query") or query,
            "answer": answer_text,
            "results": results[: settings.xah_max_results],
            "provider": provider or "xah",
        }

    @staticmethod
    def _answer_text(answer: Any) -> str:
        if isinstance(answer, dict):
            for key in ("text", "content", "answer", "summary"):
                value = answer.get(key)
                if value not in (None, ""):
                    return str(value).strip()
            return ""
        return str(answer or "").strip()

    @classmethod
    def _result_items(cls, raw_results: Any) -> list[Any]:
        if raw_results is None:
            return []
        if isinstance(raw_results, dict):
            if cls._extract_url(raw_results):
                return [raw_results]
            for key in ("results", "items", "links", "data"):
                if key in raw_results:
                    return cls._result_items(raw_results.get(key))
            return []
        if isinstance(raw_results, (list, tuple, set)):
            items: list[Any] = []
            for value in raw_results:
                items.extend(cls._result_items(value) if isinstance(value, (dict, list, tuple, set)) else [value])
            return items
        return [raw_results]

    @staticmethod
    def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = item.get(key)
            if isinstance(value, (str, int, float)) and str(value).strip():
                return str(value).strip()
        return ""

    @classmethod
    def _extract_url(cls, item: Any) -> str:
        if isinstance(item, str):
            candidates = cls._extract_urls_from_text(item)
            return candidates[0] if candidates else ""
        if not isinstance(item, dict):
            return ""
        for key in ("url", "link", "href", "source_url", "source", "uri"):
            value = item.get(key)
            if isinstance(value, str):
                candidates = cls._extract_urls_from_text(value)
                if candidates:
                    return candidates[0]
            elif isinstance(value, dict):
                nested = cls._extract_url(value)
                if nested:
                    return nested
        return ""

    @staticmethod
    def _extract_urls_from_text(value: str) -> list[str]:
        if not value:
            return []
        matches = re.findall(r"https?://[^\s<>\"']+", str(value))
        cleaned: list[str] = []
        for match in matches:
            url = re.sub(r"[\*\'\"`]+", "", match).rstrip(".,;:!?)]}>/")
            if url and url not in cleaned:
                cleaned.append(url)
        return cleaned

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

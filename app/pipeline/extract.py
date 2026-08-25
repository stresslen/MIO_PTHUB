import json
import logging
import re
import requests
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
from app.config import settings
from app.services.keyword_service import keyword_service
from app.models.scoring_rule import AIExtractionResult
from app.pipeline.normalize import (
    clean_html,
    normalize_unicode,
    parse_vietnamese_currency,
    parse_datetime,
    extract_location,
    extract_contact_info,
    normalize_phone_numbers,
)

logger = logging.getLogger(__name__)


def prefilter_keywords(title: str, text: str) -> Tuple[bool, List[str], List[str]]:
    """
    Fast, strict pre-filtering by keywords using Unicode word boundary matching.
    Prevents false positive substring matches (e.g. 'ai' in 'tại/loại', 'iot' in 'biotin', 'gis' in 'logistics').
    Returns:
      (is_relevant, matched_keywords, matched_categories)
    """
    combined_text = f"{title} {text}".lower()
    keywords_cfg = keyword_service.get_config()
    
    matched_keywords: List[str] = []
    matched_categories: List[str] = []

    # 1. Scan active keyword groups
    groups = keywords_cfg.get("keyword_groups", {})
    for g_key, g_val in groups.items():
        g_name = g_val.get("name", g_key)
        kws = g_val.get("keywords", [])
        matched_in_g = []
        for kw in kws:
            kw_clean = kw.strip().lower()
            if not kw_clean:
                continue
            # Use Unicode word boundary regex to avoid partial substring matching
            pattern = rf"(?<!\w){re.escape(kw_clean)}(?!\w)"
            if re.search(pattern, combined_text):
                matched_in_g.append(kw)

        if matched_in_g:
            matched_keywords.extend(matched_in_g)
            matched_categories.append(g_name)

    # 2. Backward compatibility with categories list if present
    for cat in keywords_cfg.get("categories", []):
        cat_name = cat.get("name")
        cat_keywords = cat.get("keywords", [])
        has_match = False
        for kw in cat_keywords:
            kw_clean = kw.strip().lower()
            pattern = rf"(?<!\w){re.escape(kw_clean)}(?!\w)"
            if re.search(pattern, combined_text):
                matched_keywords.append(kw)
                has_match = True
        if has_match and cat_name not in matched_categories:
            matched_categories.append(cat_name)

    is_relevant = len(matched_keywords) > 0
    return is_relevant, list(set(matched_keywords)), list(set(matched_categories))


class AIQuotaOrAPIError(Exception):
    """Raised when Gemini AI API returns a 429 quota error or rate limit."""
    pass


class AIAuthenticationError(AIQuotaOrAPIError):
    """Raised when the configured AI credential is rejected."""
    pass


class AIExtractor:
    """
    AI Extraction Engine supporting configured OpenAI-compatible or Gemini APIs.
    Extraction failures are surfaced and unfinished data is never persisted.
    """

    def extract(self, title: str, raw_content: str, source: str = "", raise_on_api_error: bool = False) -> AIExtractionResult:
        """Extract with the configured AI provider only; never synthesize fallback data."""
        clean_text = clean_html(raw_content)
        if settings.ai_provider == "openai":
            if not settings.openai_api_key:
                raise AIAuthenticationError("Chưa cấu hình OPENAI_API_KEY cho AI extraction")
            try:
                return self._extract_openai(title, clean_text, source)
            except AIAuthenticationError:
                raise
            except Exception as exc:
                message = str(exc)
                if any(key in message.lower() for key in ("401", "403", "unauthorized", "invalid api key")):
                    raise AIAuthenticationError(f"OpenAI authentication error: {message}") from exc
                raise AIQuotaOrAPIError(f"OpenAI extraction failed: {message}") from exc

        if settings.ai_provider == "gemini":
            if not settings.gemini_api_key:
                raise AIAuthenticationError("Chưa cấu hình GEMINI_API_KEY cho AI extraction")
            try:
                return self._extract_gemini(title, clean_text, source)
            except AIAuthenticationError:
                raise
            except Exception as exc:
                message = str(exc)
                if any(key in message.lower() for key in ("401", "403", "unauthorized", "invalid api key")):
                    raise AIAuthenticationError(f"Gemini authentication error: {message}") from exc
                raise AIQuotaOrAPIError(f"Gemini extraction failed: {message}") from exc

        raise AIAuthenticationError(f"AI_PROVIDER không được hỗ trợ: {settings.ai_provider}")


    def _extract_org_name(self, title: str, text: str) -> Optional[str]:
        """Extract the accountable organization, preferring explicit source labels."""
        combined = f"{title}\n{text}"
        boilerplate = re.compile(r"Bảng giá|Danh sách|TOP 10|Tra cứu|không tìm được|Đăng nhập|Đăng ký", re.IGNORECASE)

        # Procurement portals expose the highest-confidence organization in labelled fields.
        labelled_patterns = [
            r"(?:Tên\s+)?(?:Chủ đầu tư|Bên mời thầu|Đơn vị yêu cầu|Cơ quan ban hành|Đơn vị thực hiện|Cơ quan phê duyệt)"
            r"\s*:?\s*(?!khác\b|từng\b|hoặc\b)(.{4,240}?)(?=\n|\s+(?:Mã|Tên KHLCNT|Tên gói thầu|Địa chỉ|Số quyết định|Quyết định|Phân loại)\b|$)",
        ]
        for pattern in labelled_patterns:
            for match in re.finditer(pattern, combined, re.IGNORECASE):
                candidate = normalize_unicode(match.group(1)).strip(" :-,.;")
                if 4 <= len(candidate) <= 220 and not boilerplate.search(candidate):
                    return candidate

        # News/policy articles: capture the organization that performs the stated action.
        org_prefix = (
            r"UBND|Ủy ban nhân dân|HĐND|Sở|Ban Quản lý(?: dự án)?|Ban Khoa học, Công nghệ và Môi trường"
            r"|Ban Chỉ đạo|Bộ|Cục|Tổng cục|Trung tâm|Văn phòng|Viện|Chi nhánh"
            r"|Tổng công ty|Công ty|Tập đoàn|Bệnh viện|Trường Đại học"
        )
        actor_pattern = (
            rf"(?:{org_prefix})\s+[^\n.;]{{2,180}}?"
            r"(?=\s+(?:thông báo|mời|đã|sẽ|vừa|tiếp tục|triển khai|ban hành|ký kết|có nhu cầu|lựa chọn|đề nghị|yêu cầu)\b|[.;\n]|$)"
        )
        for match in re.finditer(actor_pattern, combined, re.IGNORECASE):
            candidate = normalize_unicode(match.group(0)).strip(" :-,.;")
            if 4 <= len(candidate) <= 200 and not boilerplate.search(candidate):
                return candidate

        # Title prefix, e.g. "Bộ X: Ban hành...".
        prefix_match = re.match(r"^([^:–-]+)[:–-]", title)
        if prefix_match:
            candidate = normalize_unicode(prefix_match.group(1))
            if re.search(rf"^(?:{org_prefix})\b", candidate, re.IGNORECASE) and not boilerplate.search(candidate):
                return candidate[:200].strip()

        return None

    def _extract_deadline(self, text: str) -> Optional[str]:
        """Detect submission deadline / closing date."""
        patterns = [
            r"(?:Thời điểm đóng thầu|Hạn cuối nộp|Thời hạn nộp hồ sơ|Đóng thầu lúc|Hạn chót)\s*:\s*([^\n,;]+)",
            r"(?:đóng thầu|hạn nộp)\s*(?:vào|ngày|trước)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}(?:\s+\d{1,2}:\d{1,2})?)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                dt = parse_datetime(m.group(1))
                if dt:
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
        return None

    def _generate_need_summary(self, title: str, text: str, categories: List[str]) -> Tuple[str, List[str]]:
        """Construct a concise 1-3 sentence summary of the procurement / project requirement."""
        evidence: List[str] = []
        
        # Look for core requirement sentences
        sentences = re.split(r"[.\n]+", text)
        relevant_sentences = []
        for s in sentences:
            s_clean = normalize_unicode(s)
            if any(kw in s_clean.lower() for kw in ["triển khai", "xây dựng", "thuê dịch vụ", "nâng cấp", "số hóa", "phần mềm", "ocr", "thị giác", "camera", "trí tuệ nhân tạo"]):
                if len(s_clean) > 20 and len(s_clean) < 250:
                    relevant_sentences.append(s_clean)
                    evidence.append(s_clean)
                    if len(evidence) >= 3:
                        break

        if relevant_sentences:
            summary = ". ".join(relevant_sentences[:2]) + "."
        else:
            summary = title.strip()
            if not summary.endswith("."):
                summary += "."
            evidence.append(title.strip())

        return summary, evidence

    @staticmethod
    def _keep_source_backed_website(data: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Reject a website proposed by AI unless its domain appears in the source text."""
        cleaned = dict(data)
        website = str(cleaned.get("organization_website") or "").strip()
        if not website:
            return cleaned
        candidate = website if "://" in website else f"https://{website}"
        host = (urlparse(candidate).hostname or "").lower().removeprefix("www.")
        source_text = str(text or "").lower()
        if not host or host not in source_text:
            logger.warning("Loại organization_website không có bằng chứng trực tiếp trong bài gốc: %s", website)
            cleaned["organization_website"] = None
        return cleaned

    def _extract_openai(self, title: str, text: str, source: str = "") -> AIExtractionResult:
        """Call OpenAI API using structured output."""
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        
        prompt = self._extraction_prompt(title, text, source)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        data = json.loads(content or "{}")
        data = self._keep_source_backed_website(data, text)
        return AIExtractionResult(**self._normalize_ai_data(data))

    @staticmethod
    def _parse_json_object(content: str) -> Dict[str, Any]:
        clean_content = content.strip()
        if clean_content.startswith("```"):
            clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content, flags=re.IGNORECASE)
            clean_content = re.sub(r"\s*```$", "", clean_content)
        json_match = re.search(r"\{.*\}", clean_content, re.DOTALL)
        if not json_match:
            raise ValueError("Gemini không trả về JSON object hợp lệ")
        return json.loads(json_match.group(0))

    def _call_gemini_json(self, prompt: str) -> Dict[str, Any]:
        base_url = settings.gemini_base_url or settings.ai_base_url
        if base_url or settings.gemini_api_key.startswith("sk-"):
            endpoint = base_url or "https://api.openai.com/v1"
            if not endpoint.endswith("/chat/completions"):
                endpoint = f"{endpoint.rstrip('/')}/chat/completions"
            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {settings.gemini_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.gemini_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                },
                timeout=settings.llm_timeout_seconds,
            )
            if response.status_code in (401, 403):
                raise AIAuthenticationError(
                    f"Custom AI Gateway rejected credentials: {response.status_code}"
                )
            if not response.ok:
                raise ValueError(f"Custom AI Gateway extraction error: {response.status_code}")
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._parse_json_object(content)

        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        response = model.generate_content(prompt)
        return self._parse_json_object(response.text)

    @staticmethod
    def _extraction_prompt(title: str, text: str, source: str = "") -> str:
        return f"""Bạn là bộ trích xuất vòng 1 có kiểm chứng cho cơ hội B2B/B2G tại Việt Nam.

NGUỒN CRAWLER: {source or "không xác định"}
TIÊU ĐỀ: {title}
NỘI DUNG GỐC:
{text[:16000]}

QUY TẮC BẮT BUỘC:
1. Chỉ trích xuất dữ liệu xuất hiện trực tiếp trong bài gốc. Vòng 1 tuyệt đối không gọi search và không suy đoán.
2. organization_name là tổ chức có nhu cầu, Chủ đầu tư hoặc Bên mời thầu. Ưu tiên nhãn "Chủ đầu tư", "Bên mời thầu", "Cơ quan ban hành".
3. Không đủ bằng chứng thì trả null; không trả "Đang cập nhật", "Không rõ" và không tự đặt tên tổ chức.
4. organization_website chỉ là website/domain xuất hiện trực tiếp trong bài gốc. Không được đoán website theo tên tổ chức.
5. need_summary chỉ tóm tắt nhu cầu/hành động nêu rõ; không thêm sản phẩm, ngân sách hay kế hoạch ngoài nguồn.
6. budget_value chỉ điền khi có ngân sách/giá gói thầu rõ ràng.
7. deadline chỉ là hạn nộp/đóng thầu/hạn chót có nhãn rõ. KHÔNG dùng ngày đăng bài, ngày cập nhật, phê duyệt, sự kiện hoặc ngày trong tiêu đề.
8. Ngày đăng do crawler lấy từ metadata riêng, không suy diễn trong JSON này.
9. evidence phải trực tiếp chứng minh tên tổ chức, nhu cầu, ngân sách/deadline và website nếu có.

Trả về duy nhất 1 JSON object hợp lệ:
{{
  "organization_name": "Tên đầy đủ có bằng chứng hoặc null",
  "organization_type": "government" hoặc "enterprise" hoặc "other" hoặc null,
  "organization_website": "URL xuất hiện trong bài hoặc null",
  "organization_tax_code": "mã số thuế/mã bên mời thầu hoặc null",
  "need_summary": "Tóm tắt nhu cầu trong 1-3 câu hoặc null",
  "need_categories": [],
  "budget_value": null,
  "budget_text": null,
  "location": null,
  "contact_name": null,
  "contact_email": null,
  "contact_phone": null,
  "deadline": "YYYY-MM-DD hoặc null",
  "relevance": 0.0,
  "evidence": ["bằng chứng trực tiếp từ bài gốc"],
  "missing_information": []
}}
"""

    @staticmethod
    def _normalize_ai_data(data: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(data)
        cleaned["contact_phone"] = normalize_phone_numbers(cleaned.get("contact_phone"))
        website = str(cleaned.get("organization_website") or "").strip()
        if website and "://" not in website:
            website = f"https://{website}"
        cleaned["organization_website"] = website or None
        org_type = str(cleaned.get("organization_type") or "").strip().lower()
        cleaned["organization_type"] = org_type if org_type in {"government", "enterprise", "other"} else None
        return cleaned

    def _extract_gemini(self, title: str, text: str, source: str = "") -> AIExtractionResult:
        """Round one uses Gemini only on the crawled source; XAH belongs to round two."""
        data = self._call_gemini_json(self._extraction_prompt(title, text, source))
        data = self._keep_source_backed_website(data, text)
        return AIExtractionResult(**self._normalize_ai_data(data))


# Singleton instance
ai_extractor = AIExtractor()

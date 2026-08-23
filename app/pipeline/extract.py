import json
import logging
import re
import requests
from typing import Dict, List, Optional, Tuple, Any
from app.config import settings, get_keywords_config
from app.models.scoring_rule import AIExtractionResult
from app.pipeline.normalize import (
    clean_html,
    normalize_unicode,
    parse_vietnamese_currency,
    parse_datetime,
    extract_location,
    extract_contact_info,
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
    keywords_cfg = get_keywords_config()
    
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


class AIExtractor:
    """
    AI Extraction Engine supporting LLM APIs (OpenAI, Gemini) with
    intelligent Rule & NLP fallback when operating offline.
    """

    def __init__(self):
        self.keywords_config = get_keywords_config()

    def extract(self, title: str, raw_content: str, source: str = "", raise_on_api_error: bool = False) -> AIExtractionResult:
        """Main extraction method with automatic provider selection and fallback."""
        clean_text = clean_html(raw_content)
        
        # 1. Try LLM if configured
        if settings.ai_provider == "openai" and settings.openai_api_key:
            try:
                return self._extract_openai(title, clean_text, source)
            except Exception as e:
                logger.warning(f"OpenAI extraction failed: {e}")
                if raise_on_api_error or any(k in str(e).lower() for k in ["429", "quota", "rate", "limit"]):
                    raise AIQuotaOrAPIError(f"OpenAI error: {e}")
        elif settings.ai_provider == "gemini" and settings.gemini_api_key:
            try:
                return self._extract_gemini(title, clean_text, source)
            except Exception as e:
                logger.warning(f"Gemini extraction error: {e}")
                if raise_on_api_error or any(k in str(e).lower() for k in ["429", "quota", "rate", "limit", "resource_exhausted", "503"]):
                    raise AIQuotaOrAPIError(f"Gemini API Error: {e}")

        # 2. Rule-based / NLP Extractor (High precision & deterministic)
        return self._extract_rule_based(title, clean_text, source)

    def _extract_rule_based(self, title: str, text: str, source: str = "") -> AIExtractionResult:
        """Rule-based NLP extractor that parses Vietnamese government and B2B texts."""
        combined = f"{title}\n{text}"
        
        # 1. Categories and keywords
        is_relevant, matched_kw, matched_cats = prefilter_keywords(title, text)
        
        # 2. Extract Organization Name
        org_name = self._extract_org_name(title, text)
        org_type = "government" if any(w in (org_name or "").lower() for w in ["sở", "ban", "ubnd", "cục", "bộ", "trung tâm", "viện", "tỉnh", "thành phố"]) else "enterprise"

        # 3. Extract Budget
        budget_val, budget_txt = parse_vietnamese_currency(text)
        if not budget_val:
            budget_val, budget_txt = parse_vietnamese_currency(title)

        # 4. Extract Location
        location = extract_location(text) or extract_location(title)

        # 5. Extract Contact
        c_name, c_email, c_phone = extract_contact_info(text)

        # 6. Extract Deadline
        deadline_str = self._extract_deadline(text)

        # 7. Generate Need Summary & Evidence
        need_summary, evidence = self._generate_need_summary(title, text, matched_cats)

        # 8. Compute Relevance
        base_relevance = 0.5 if is_relevant else 0.2
        if budget_val and budget_val > 1_000_000_000:
            base_relevance += 0.2
        if any(cat in ["OCR / Số hóa tài liệu", "Computer Vision / Thị giác máy tính", "Voice AI / Trợ lý giọng nói", "LLM / AI / Trí tuệ nhân tạo"] for cat in matched_cats):
            base_relevance += 0.2
        relevance = min(1.0, round(base_relevance, 2))

        return AIExtractionResult(
            organization_name=org_name,
            organization_type=org_type,
            need_summary=need_summary,
            need_categories=matched_cats,
            budget_value=budget_val,
            budget_text=budget_txt,
            location=location,
            contact_name=c_name,
            contact_email=c_email,
            contact_phone=c_phone,
            deadline=deadline_str,
            relevance=relevance,
            evidence=evidence,
            confidence=0.88 if is_relevant else 0.40,
        )

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
        return AIExtractionResult(**self._apply_deterministic_fallback(data, title, text))

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
    def _needs_xah_search(data: Dict[str, Any]) -> bool:
        explicit_request = data.get("needs_web_search") is True
        missing_core = not data.get("organization_name") or not data.get("need_summary")
        return bool(settings.xah_api_key and (explicit_request or missing_core))

    @staticmethod
    def _extraction_prompt(title: str, text: str, source: str = "", search_context: str = "") -> str:
        supplemental = f"""
DỮ LIỆU BỔ SUNG TỪ XAH SEARCH (nguồn phụ):
{search_context}

Chỉ dùng XAH để bổ sung trường còn thiếu. Nếu XAH mâu thuẫn với bài gốc thì GIỮ dữ liệu bài gốc.
Mọi evidence lấy từ XAH phải ghi kèm URL.
""" if search_context else ""
        return f"""Bạn là bộ trích xuất dữ liệu có kiểm chứng cho cơ hội B2B/B2G tại Việt Nam.

NGUỒN CRAWLER: {source or "không xác định"}
TIÊU ĐỀ: {title}
NỘI DUNG GỐC:
{text[:5000]}
{supplemental}
QUY TẮC BẮT BUỘC:
1. organization_name là tổ chức chịu trách nhiệm, có nhu cầu, là Chủ đầu tư hoặc Bên mời thầu. Ưu tiên tuyệt đối trường có nhãn "Chủ đầu tư", "Bên mời thầu", "Cơ quan ban hành" trong bài gốc.
2. Với bài báo/chính sách, chọn cơ quan ban hành/chủ trì hành động; không chọn tên cá nhân, tên website, đơn vị chỉ được nhắc thoáng qua hoặc cụm chung chung.
3. Không bao giờ trả "Đang cập nhật", "Không rõ" hay tự bịa tên. Không đủ bằng chứng thì trả null và yêu cầu web search nếu thông tin này quan trọng.
4. need_summary chỉ tóm tắt nhu cầu/hành động được nêu rõ; không thêm sản phẩm, ngân sách hay kế hoạch không có trong nguồn.
5. budget_value chỉ được điền khi có con số ngân sách/giá gói thầu rõ ràng; không biến thời lượng, mã gói hoặc số lượng thành tiền.
6. deadline chỉ là hạn nộp/đóng thầu/hạn chót được gắn nhãn rõ ràng. KHÔNG dùng ngày đăng bài, ngày cập nhật, ngày phê duyệt, ngày sự kiện hay một ngày xuất hiện trong tiêu đề làm deadline.
7. Ngày đăng do crawler lấy từ metadata riêng, không suy diễn trong JSON này.
8. evidence phải trực tiếp chứng minh organization_name, nhu cầu và ngân sách/deadline nếu có.

Trả về duy nhất 1 JSON object hợp lệ:
{{
  "organization_name": "Tên đầy đủ có bằng chứng hoặc null",
  "organization_type": "government" hoặc "enterprise" hoặc "other",
  "need_summary": "Tóm tắt nhu cầu trong 1-3 câu hoặc null",
  "need_categories": ["OCR / Số hóa tài liệu", "Computer Vision / Thị giác máy tính", "Voice AI / Trợ lý giọng nói", "LLM / AI / Trí tuệ nhân tạo", "Chuyển đổi số", "Data Warehouse / Cloud", "Phần mềm"],
  "budget_value": <ngân sách quy đổi VNĐ hoặc null>,
  "budget_text": "chuỗi ngân sách nguyên văn hoặc null",
  "location": "tỉnh/thành hoặc null",
  "contact_name": "tên người liên hệ hoặc null",
  "contact_email": "email hoặc null",
  "contact_phone": "số điện thoại hoặc null",
  "deadline": "YYYY-MM-DD hoặc null",
  "relevance": <0.0 đến 1.0>,
  "evidence": ["1-3 bằng chứng trực tiếp; bằng chứng XAH phải kèm URL"],
  "needs_web_search": <true chỉ khi thiếu thông tin quan trọng có thể tìm công khai>,
  "missing_information": ["thông tin quan trọng còn thiếu"],
  "search_query": "truy vấn ngắn gồm tiêu đề/tổ chức và loại thông tin cần tìm; null nếu không cần"
}}
Không yêu cầu search chỉ vì thiếu email, số điện thoại hoặc ngân sách mà nguồn không công bố.
"""

    def _apply_deterministic_fallback(self, data: Dict[str, Any], title: str, text: str) -> Dict[str, Any]:
        cleaned = dict(data)
        organization = str(cleaned.get("organization_name") or "").strip()
        if organization.lower() in {"", "đang cập nhật", "không rõ", "n/a", "null"}:
            cleaned["organization_name"] = self._extract_org_name(title, text)
        return cleaned

    def _extract_gemini(self, title: str, text: str, source: str = "") -> AIExtractionResult:
        """Gemini extracts once, asks XAH only when it identifies a material information gap."""
        initial_data = self._call_gemini_json(self._extraction_prompt(title, text, source))
        if not self._needs_xah_search(initial_data):
            return AIExtractionResult(**self._apply_deterministic_fallback(initial_data, title, text))

        query = str(initial_data.get("search_query") or "").strip()
        if not query:
            organization = initial_data.get("organization_name") or ""
            query = f'"{title}" {organization}'.strip()

        try:
            from app.services.xah_search_service import xah_search_service

            logger.info("Gemini yêu cầu XAH bổ sung dữ liệu: %s", query[:200])
            search_data = xah_search_service.search(query[:500])
            if not search_data.get("answer") and not search_data.get("results"):
                return AIExtractionResult(**self._apply_deterministic_fallback(initial_data, title, text))

            enriched_data = self._call_gemini_json(
                self._extraction_prompt(title, text, source, xah_search_service.to_gemini_context(search_data))
            )
            source_urls = [item["url"] for item in search_data.get("results") or [] if item.get("url")]
            evidence = list(enriched_data.get("evidence") or [])
            for url in source_urls:
                source_note = f"Nguồn bổ sung XAH: {url}"
                if source_note not in evidence:
                    evidence.append(source_note)
            enriched_data["evidence"] = evidence
            enriched_data["web_search_used"] = True
            enriched_data["search_sources"] = source_urls
            return AIExtractionResult(**self._apply_deterministic_fallback(enriched_data, title, text))
        except Exception as exc:
            logger.warning("XAH enrichment thất bại, giữ kết quả Gemini ban đầu: %s", exc)
            return AIExtractionResult(**self._apply_deterministic_fallback(initial_data, title, text))


# Singleton instance
ai_extractor = AIExtractor()

import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional
import requests

from app.config import settings
from app.models.scoring_rule import ScoreResult, ScoreBreakdownItem
from app.pipeline.extract import AIAuthenticationError, AIQuotaOrAPIError
from app.pipeline.normalize import utc_now

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

        if settings.ai_provider == "openai":
            if not settings.openai_api_key:
                raise AIAuthenticationError("Chưa cấu hình OPENAI_API_KEY cho AI scoring")
            try:
                result = self._evaluate_with_openai(**common)
            except (AIAuthenticationError, AIQuotaOrAPIError):
                raise
            except Exception as exc:
                raise AIQuotaOrAPIError(
                    f"OpenAI scoring trả dữ liệu không hợp lệ: {exc}"
                ) from exc
            if result is None:
                raise AIQuotaOrAPIError("OpenAI scoring không trả về kết quả hợp lệ")
            return result

        raise AIAuthenticationError(f"AI_PROVIDER không được hỗ trợ: {settings.ai_provider}")

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
        now_str = utc_now().strftime("%Y-%m-%d")
        pub_str = published_at.strftime("%Y-%m-%d") if published_at else "Chưa rõ"
        deadline_str = deadline.strftime("%Y-%m-%d") if deadline else "Chưa rõ"
        budget_str = f"{budget_value:,.0f} VNĐ" if budget_value else "Chưa xác định"

        prompt = f"""
Bạn là Chuyên gia Cao cấp về AI Lead Intelligence & B2B/B2G Sales Strategy trong lĩnh vực Chuyển đổi số & AI.
Nhiệm vụ của bạn là phân tích sâu và chấm điểm khách hàng tiềm năng (0 - 100 điểm) dựa trên các tiêu chí chuẩn mực quốc tế sau:

=== TIÊU CHÍ CHẤM ĐIỂM CHI TIẾT (0 - 100 ĐIỂM) ===
1. NHU CẦU SỐ HÓA, CHUYỂN ĐỔI SỐ HOẶC ỨNG DỤNG AI (Tối đa +25 điểm):
   - Chỉ cần đơn vị/cơ quan/doanh nghiệp có nhu cầu, chủ trương, kế hoạch, gói thầu, đề án hoặc dự án liên quan đến: **Số hóa, Chuyển đổi số, Ứng dụng AI, Nâng cấp hệ thống CNTT/Phần mềm, Xây dựng cơ sở dữ liệu/Nền tảng số** là được cộng tối đa +25 điểm (KHÔNG yêu cầu phải nêu chi tiết bài toán hay thuật toán cụ thể).
2. QUY MÔ NGÂN SÁCH & KHẢ NĂNG CHI TRẢ (Tối đa +25 điểm):
   - Ngân sách >= 3 tỷ VNĐ (+20 điểm).
   - Ngân sách >= 5 tỷ VNĐ (+25 điểm).
   - Ngân sách < 3 tỷ hoặc chưa ghi số tiền nhưng là dự án/đề án cấp Tỉnh/Bộ ngành/Tổng công ty (+10 đến +15 điểm).
3. ĐỊA BÀN CHIẾN LƯỢC (Tối đa +10 điểm):
   - Triển khai tại: Hà Nội, TP.HCM, Đà Nẵng, Quảng Ninh, Hải Phòng, Bình Dương, Đồng Nai, Cần Thơ hoặc cơ quan cấp Trung ương (+10 điểm).
4. KHỚP NĂNG LỰC CÔNG NGHỆ LÕI (Tối đa +15 điểm):
   - Đơn vị cần giải pháp về: Số hóa hồ sơ/OCR, Chuyển đổi số, Phần mềm nghiệp vụ, Ứng dụng AI (Chatbot, Voice, Camera, LLM, Xử lý dữ liệu) (+15 điểm).
5. KHẢ NĂNG TIẾP CẬN & LIÊN HỆ (Tối đa +10 điểm):
   - Có email, số điện thoại hoặc đầu mối liên hệ công khai (+10 điểm).
6. TÍNH CẤP BÁCH & THỜI HẠN (Tối đa +10 điểm / Phạt -30 điểm nếu quá hạn):
   - Còn >= 5 ngày trước hạn đóng thầu/hạn tiếp cận (+10 điểm).
   - Tin đăng mới trong vòng 3 ngày (+5 điểm).
   - Hạn tiếp cận đã quá hạn (Trừ -30 điểm).
7. ĐIỂM TRỪ NẾU HOÀN TOÀN KHÔNG LIÊN QUAN CNTT/CĐS (Phạt -20 điểm):
   - Chỉ phạt điểm khi tin tức hoàn toàn không liên quan đến công nghệ thông tin/chuyển đổi số (ví dụ: xây lắp công trình cầu đường thuần túy, hoạt động thể thao...).

=== QUY TẮC PHÂN LUỒNG HÀNH ĐỘNG ===
- 90 - 100 điểm: "CALL" (Hot Lead - Ưu tiên gọi điện & tiếp cận trực tiếp ngay lập tức).
- 80 - 89 điểm: "EMAIL" (Qualified Lead - Chuẩn bị tài liệu & gửi email chào giải pháp chuyên sâu).
- 0 - 79 điểm: "NURTURE" (Nurturing - Marketing theo dõi, nuôi dưỡng & làm giàu thông tin).

=== THÔNG TIN CƠ HỘI CẦN ĐÁNH GIÁ ===
- Tiêu đề: {title}
- Nhu cầu trích xuất: {need_summary or 'Chưa có tóm tắt'}
- Phân loại lĩnh vực: {', '.join(need_categories)}
- Ngân sách: {budget_str}
- Địa bàn: {location or 'Toàn quốc'}
- Liên hệ: Email: {contact_email or 'Không có'} | SĐT: {contact_phone or 'Không có'}
- Ngày đăng: {pub_str} | Hạn chót: {deadline_str} | Ngày hiện tại: {now_str}
- Mức độ phù hợp ban đầu: {relevance}
- Minh chứng trích xuất: {' | '.join(evidence[:3])}

=== ĐỊNH DẠNG ĐẦU RA JSON BẮT BUỘC ===
Trả về duy nhất 1 JSON object hợp lệ:
{{
  "total_score": <số nguyên từ 0 đến 100>,
  "recommended_action": "CALL" | "EMAIL" | "NURTURE",
  "score_reasons": [
    "+25 Có gói thầu cụ thể về OCR và số hóa hồ sơ",
    "+20 Ngân sách lớn 4.5 tỷ VNĐ (>= 3 tỷ)",
    "+10 Địa bàn chiến lược Hà Nội",
    ...
  ],
  "breakdown": [
    {{"rule_name": "demand_specificity", "points": 25, "reason": "..."}},
    {{"rule_name": "budget_size", "points": 20, "reason": "..."}}
  ],
  "sales_strategy_suggestion": "<1-2 câu gợi ý cho Sales về thông điệp tiếp cận và giải pháp trọng tâm nên chào>"
}}
"""

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
        action = parsed.get("recommended_action", "NURTURE")
        if score >= 90:
            action = "CALL"
        elif score >= 80:
            action = "EMAIL"
        else:
            action = "NURTURE"

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

    def _evaluate_with_openai(
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
    ) -> Optional[ScoreResult]:
        """Fallback to OpenAI API if configured."""
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        
        prompt = f"""
        Chấm điểm Lead B2B/B2G từ 0 đến 100 điểm theo tiêu chí:
        - Tiêu đề: {title}
        - Nhu cầu: {need_summary}
        - Lĩnh vực: {need_categories}
        - Ngân sách: {budget_value}
        - Địa bàn: {location}
        - Contact: Email={contact_email}, Phone={contact_phone}
        - Deadline: {deadline}
        
        Trả về JSON:
        {{
          "total_score": 0..100,
          "recommended_action": "CALL" | "EMAIL" | "NURTURE",
          "score_reasons": ["+X lý do 1", "+Y lý do 2"],
          "sales_strategy_suggestion": "Gợi ý tiếp cận"
        }}
        """
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content or "{}")
        score = max(0, min(100, int(parsed.get("total_score", 0))))
        action = "CALL" if score >= 90 else ("EMAIL" if score >= 80 else "NURTURE")

        return ScoreResult(
            total_score=score,
            recommended_action=action,
            reasons=parsed.get("score_reasons", []),
            sales_strategy_suggestion=parsed.get("sales_strategy_suggestion"),
            evaluated_by="ai_openai",
        )



scoring_engine = AIScoringEngine()

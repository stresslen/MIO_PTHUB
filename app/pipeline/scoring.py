import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional
import requests

from app.config import settings, get_scoring_config
from app.models.scoring_rule import ScoreResult, ScoreBreakdownItem
from app.pipeline.normalize import utc_now

logger = logging.getLogger(__name__)


class AIScoringEngine:
    """
    AI-Powered Lead Scoring Engine.
    Uses Google Gemini (e.g. gemini-2.0-flash-lite / gemini-1.5-flash) to evaluate
    and score B2B/B2G leads across comprehensive multi-dimensional criteria.
    Includes a robust rule-based fallback when GEMINI_API_KEY is not yet configured.
    """

    def __init__(self):
        self.config = get_scoring_config()

    def reload_config(self):
        self.config = get_scoring_config()

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
        """
        Evaluate and score a lead.
        Prioritizes Google Gemini AI scoring when GEMINI_API_KEY is present,
        and gracefully falls back to deterministic rule scoring when offline / key not set.
        """
        # 1. Check if Gemini API key is configured
        if settings.gemini_api_key:
            try:
                ai_res = self._evaluate_with_gemini(
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
                    evidence=raw_evidence or [],
                )
                if ai_res:
                    return ai_res
            except Exception as e:
                logger.warning(f"Gemini AI Scoring failed, falling back to rule-based: {e}")

        # 2. Check if OpenAI API key is configured as alternate
        if settings.openai_api_key and settings.ai_provider == "openai":
            try:
                ai_res = self._evaluate_with_openai(
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
                )
                if ai_res:
                    return ai_res
            except Exception as e:
                logger.warning(f"OpenAI AI Scoring failed, falling back to rule-based: {e}")

        # 3. Rule-Based Fallback Engine (Fully featured & deterministic)
        return self._evaluate_rule_based(
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
            else:
                logger.warning(f"Custom AI Gateway returned status {resp.status_code}: {resp.text[:200]}")
                return None

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

    def _evaluate_rule_based(
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
    ) -> ScoreResult:
        """
        Comprehensive rule-based scoring engine (0-100) running offline.
        """
        weights = self.config.get("weights", {})
        breakdown: List[ScoreBreakdownItem] = []
        reasons: List[str] = []
        raw_score = 0

        combined_text = f"{title} {need_summary or ''}".lower()

        # 1. Broad Digitization / Digital Transformation / AI Need (+25)
        has_tech_need = any(
            kw in combined_text for kw in [
                "số hóa", "chuyển đổi số", "ứng dụng ai", "trí tuệ nhân tạo", "ai", "ocr", "camera", "voice", "phần mềm",
                "cơ sở dữ liệu", "nền tảng số", "hạ tầng số", "công nghệ thông tin", "cntt", "gói thầu", "mời thầu",
                "dự án", "thuê dịch vụ", "xây dựng hệ thống", "nâng cấp", "triển khai", "mua sắm", "tin học hóa", "thông minh"
            ]
        )
        if has_tech_need:
            pts = weights.get("concrete_project_or_tender", 25)
            raw_score += pts
            reason = f"+{pts} Có nhu cầu về Số hóa, Chuyển đổi số, Ứng dụng AI hoặc Phần mềm/CNTT"
            reasons.append(reason)
            breakdown.append(ScoreBreakdownItem(rule_name="tech_transformation_need", points=pts, reason=reason))

        # 2. Budget >= 3 tỷ (+20, bonus +5 if >= 5 tỷ)
        if budget_value and budget_value >= 3_000_000_000:
            pts = weights.get("budget_gte_3b", 20)
            raw_score += pts
            budget_str = f"{budget_value / 1_000_000_000:.1f} tỷ"
            reason = f"+{pts} Ngân sách lớn ({budget_str} VND >= 3 tỷ)"
            reasons.append(reason)
            breakdown.append(ScoreBreakdownItem(rule_name="budget_gte_3b", points=pts, reason=reason))

            if budget_value >= 5_000_000_000:
                bonus_pts = weights.get("budget_gte_5b_bonus", 5)
                raw_score += bonus_pts
                bonus_reason = f"+{bonus_pts} Thưởng bổ sung cho ngân sách quy mô lớn >= 5 tỷ ({budget_str} VND)"
                reasons.append(bonus_reason)
                breakdown.append(ScoreBreakdownItem(rule_name="budget_gte_5b_bonus", points=bonus_pts, reason=bonus_reason))
        elif budget_value and budget_value >= 500_000_000:
            pts = 10
            raw_score += pts
            budget_str = f"{budget_value / 1_000_000_000:.2f} tỷ"
            reason = f"+{pts} Có dự toán ngân sách rõ ràng ({budget_str} VND)"
            reasons.append(reason)
            breakdown.append(ScoreBreakdownItem(rule_name="budget_positive", points=pts, reason=reason))

        # 3. Strategic Location (+10)
        strategic_list = weights.get("strategic_locations_list", ["Hà Nội", "TP.HCM", "Đà Nẵng", "Quảng Ninh", "Hải Phòng", "Bình Dương", "Đồng Nai", "Cần Thơ"])
        if location and any(strat.lower() in location.lower() for strat in strategic_list):
            pts = weights.get("strategic_location", 10)
            raw_score += pts
            reason = f"+{pts} Địa bàn chiến lược trọng điểm ({location})"
            reasons.append(reason)
            breakdown.append(ScoreBreakdownItem(rule_name="strategic_location", points=pts, reason=reason))

        # 4. Capability Match (+15)
        core_caps = ["OCR / Số hóa tài liệu", "Computer Vision / Thị giác máy tính", "Voice AI / Trợ lý giọng nói", "LLM / AI / Trí tuệ nhân tạo", "Chuyển đổi số", "Phần mềm", "Data Warehouse / Cloud"]
        matched_core = [c for c in need_categories if any(core.lower() in c.lower() for core in core_caps)]
        if matched_core or has_tech_need:
            pts = weights.get("core_capability_match", 15)
            raw_score += pts
            caps_str = ", ".join(matched_core[:2]) if matched_core else "Số hóa / Chuyển đổi số / AI"
            reason = f"+{pts} Khớp năng lực công nghệ về {caps_str}"
            reasons.append(reason)
            breakdown.append(ScoreBreakdownItem(rule_name="core_capability_match", points=pts, reason=reason))

        # 5. Public Contact Info (+10)
        if contact_email or contact_phone:
            pts = weights.get("has_contact_info", 10)
            raw_score += pts
            c_type = "Email & Số điện thoại" if (contact_email and contact_phone) else ("Email" if contact_email else "Số điện thoại")
            reason = f"+{pts} Có thông tin liên hệ công khai ({c_type})"
            reasons.append(reason)
            breakdown.append(ScoreBreakdownItem(rule_name="has_contact_info", points=pts, reason=reason))

        # 6. Freshness <= 3 days (+5)
        now = utc_now()
        if published_at:
            age_days = (now - published_at).total_seconds() / 86400.0
            if age_days <= 3.0:
                pts = weights.get("freshness_lte_3days", 5)
                raw_score += pts
                reason = f"+{pts} Thông tin xuất bản mới ({age_days:.1f} ngày trước <= 3 ngày)"
                reasons.append(reason)
                breakdown.append(ScoreBreakdownItem(rule_name="freshness_lte_3days", points=pts, reason=reason))

        # 7. Deadline Check (+10 or -30)
        if deadline:
            time_left = (deadline - now).total_seconds() / 86400.0
            if time_left >= 5.0:
                pts = weights.get("deadline_gte_5days", 10)
                raw_score += pts
                reason = f"+{pts} Còn nhiều thời gian chuẩn bị hồ sơ tiếp cận ({int(time_left)} ngày >= 5 ngày)"
                reasons.append(reason)
                breakdown.append(ScoreBreakdownItem(rule_name="deadline_gte_5days", points=pts, reason=reason))
            elif time_left < 0:
                penalty = weights.get("expired_deadline", -30)
                raw_score += penalty
                reason = f"{penalty} Thời hạn tiếp cận / đóng thầu đã qua"
                reasons.append(reason)
                breakdown.append(ScoreBreakdownItem(rule_name="expired_deadline", points=penalty, reason=reason))

        # 8. Low relevance penalty (-15)
        if relevance < 0.4:
            penalty = weights.get("low_relevance_policy_only", -15)
            raw_score += penalty
            reason = f"{penalty} Mức độ phù hợp thấp hoặc chỉ là tin tức chính sách/tuyên truyền chung"
            reasons.append(reason)
            breakdown.append(ScoreBreakdownItem(rule_name="low_relevance", points=penalty, reason=reason))

        final_score = max(0, min(100, raw_score))

        thresholds = self.config.get("action_thresholds", {})
        hot_min = thresholds.get("hot_lead", {}).get("min_score", 90)
        qual_min = thresholds.get("qualified_lead", {}).get("min_score", 80)

        if final_score >= hot_min:
            action = "CALL"
            sales_strategy = "Hot Lead ưu tiên cao: Cử Giám đốc kinh doanh/Trưởng nhóm B2G liên hệ trực tiếp đơn vị để khảo sát nhu cầu nghiệp vụ và giới thiệu hồ sơ năng lực AI."
        elif final_score >= qual_min:
            action = "EMAIL"
            sales_strategy = "Qualified Lead: Gửi email chính thức kèm tài liệu giới thiệu giải pháp (Pitch Deck) và demo case study tương tự trong ngành."
        else:
            action = "NURTURE"
            sales_strategy = "Nurturing Lead: Đưa vào danh sách Marketing nurturing, theo dõi các văn bản chỉ đạo tiếp theo của đơn vị."

        return ScoreResult(
            total_score=final_score,
            recommended_action=action,
            reasons=reasons,
            breakdown=breakdown,
            sales_strategy_suggestion=sales_strategy,
            evaluated_by="rule_based_engine (Set GEMINI_API_KEY to activate Gemini AI)",
        )


scoring_engine = AIScoringEngine()

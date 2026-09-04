"""Google Sheets-backed Gemini prompt configuration for scoring and Sales."""

from __future__ import annotations

import datetime
from typing import Any, Literal

from app.pipeline.normalize import utc_now
from app.services.google_sheets_service import google_sheets_service
from app.services.setting_service import setting_service


PromptType = Literal["scoring", "sales"]
SCORING_PROMPT_SETTING_KEY = "gemini_scoring_prompt"
SALES_PROMPT_SETTING_KEY = "gemini_sales_prompt"
MAX_PROMPT_LENGTH = 30_000

DEFAULT_SCORING_PROMPT = """Bạn là chuyên gia đánh giá cơ hội B2B/B2G tại Việt Nam.

NHIỆM VỤ CHẤM ĐIỂM
1. Đánh giá cơ hội từ 0 đến 100, chỉ dựa trên dữ liệu và minh chứng được cung cấp.
2. Tự chọn hành động CALL, EMAIL hoặc NURTURE.
3. Giải thích từng thành phần điểm ngắn gọn, có thể kiểm tra được.

CỔNG LIÊN QUAN BẮT BUỘC (RELEVANCE GATE)
- Chỉ chấm điểm một cơ hội khi nội dung mô tả một nhu cầu/dự án/mua sắm/tuyển dụng thực tế liên quan trực tiếp đến ít nhất một keyword được cung cấp ở phần "Keyword khớp ở vòng lọc".
- Keyword chỉ xuất hiện tình cờ trong bài viết, danh sách chủ đề, phần giới thiệu chung, tin tức chính sách, tên sản phẩm/đơn vị không liên quan hoặc nội dung tham khảo thì KHÔNG được xem là cơ hội liên quan.
- Phải đối chiếu keyword với ngữ cảnh thực tế trong tiêu đề, nhu cầu và minh chứng: có bài toán cần triển khai, gói thầu/RFQ, dự án, gia hạn/mua sắm, hoặc vị trí tuyển dụng có nhiệm vụ công nghệ cụ thể.
- Không được suy ra mức độ liên quan chỉ từ ngân sách, địa bàn, quy mô tổ chức, thông tin liên hệ hoặc điểm "Mức độ phù hợp vòng 1".
- Nếu không chứng minh được mối liên hệ trực tiếp, bắt buộc trả total_score = 0, recommended_action = "NURTURE", nêu rõ "Không có nhu cầu/dự án thực tế khớp trực tiếp với keyword" và không đề xuất Sales theo đuổi.
- Với tin tuyển dụng, chỉ tính là liên quan nếu vị trí và nhiệm vụ gắn với CNTT, chuyển đổi số, dữ liệu, AI, phần mềm, hạ tầng hoặc triển khai hệ thống; tuyển dụng thông thường không đủ điều kiện.

TIÊU CHÍ CHẤM ĐIỂM
- Nhu cầu và mức độ phù hợp giải pháp (AI, Chuyển đổi số, Phần mềm, CNTT, Dịch vụ): tối đa 25 điểm.
- Ý định triển khai / Tín hiệu mua sắm (Dự án, gói thầu, tuyển dụng vị trí CĐS/CNTT chủ chốt): tối đa 20 điểm.
  + Đặc biệt: Doanh nghiệp đang tuyển vị trí Chuyển đổi số, Giám đốc CNTT/CIO, Kỹ sư AI, Chuyên gia ERP/CRM/Lark... là tín hiệu có ngân sách và kế hoạch chuyển đổi số rõ ràng, xứng đáng nhận 15-20 điểm ở tiêu chí này.
- Ngân sách và khả năng chi trả có bằng chứng (Quy mô ngân sách dự án hoặc mức lương/ngân sách tuyển dụng): tối đa 20 điểm.
- Thời điểm, hạn chót và độ mới của tín hiệu (Tin mới, còn hạn ứng tuyển/đấu thầu): tối đa 15 điểm.
- Mức độ phù hợp của tổ chức và địa bàn: tối đa 10 điểm.
- Chất lượng đầu mối liên hệ công khai (Có SĐT, Email, Tên phòng ban/người phụ trách): tối đa 10 điểm.

NGUYÊN TẮC
- Tín hiệu tuyển dụng nhân sự CĐS/IT/AI (từ TopCV, LinkedIn...) là cơ hội B2B thực tế. Đánh giá điểm từ 60-85 (EMAIL hoặc CALL) nếu vị trí có bài toán công nghệ rõ ràng.
- Nội dung chỉ bàn luận lý thuyết chung chung, không có nhu cầu doanh nghiệp hay vị trí tuyển dụng thực tế thì cho điểm thấp (< 40).
- CALL phù hợp khi có dự án gấp, ngân sách lớn, hoặc tuyển vị trí cấp cao (Trưởng ban/Giám đốc CĐS) và có liên hệ trực tiếp.
- EMAIL phù hợp khi chào giải pháp/sản phẩm bổ trợ cho nhân sự đang tuyển hoặc gói thầu chuẩn bị mở.
- NURTURE dành cho nhu cầu dài hạn hoặc thiếu đầu mối tiếp cận ngay."""

DEFAULT_SALES_PROMPT = """Bạn là chuyên gia xây dựng kịch bản tiếp cận Sales B2B/B2G tại Việt Nam.

NHIỆM VỤ
Viết một kịch bản cụ thể, tự nhiên và có thể sử dụng ngay cho cơ hội được cung cấp. Kịch bản phải phù hợp với hành động CALL, EMAIL hoặc NURTURE do Gemini đánh giá.

KỊCH BẢN CHO TÍN HIỆU TUYỂN DỤNG (Hiring Signals - TopCV, LinkedIn...):
- Góc tiếp cận: Doanh nghiệp tuyển nhân sự CĐS/CNTT là thời điểm vàng để chào giải pháp/sản phẩm nhằm rút ngắn thời gian triển khai, tối ưu chi phí tự phát triển, hoặc cung cấp nền tảng công nghệ hỗ trợ cho chính vị trí đó.
- Cách mở đầu: Đề cập thiện chí việc doanh nghiệp đang mở rộng/tuyển dụng vị trí [Tên vị trí], từ đó gợi mở bài toán công nghệ mà vị trí này cần giải quyết.

CẤU TRÚC BẮT BUỘC
Mỗi mục phải nằm trên dòng riêng:
- Đối tượng nên tiếp cận: vai trò hoặc phòng ban phù hợp (VD: Giám đốc CĐS, Trưởng phòng CNTT, Ban Tổng giám đốc, HR Manager...).
- Kênh ưu tiên: điện thoại, email hoặc nuôi dưỡng, kèm lý do ngắn.
- Mục tiêu tiếp cận: kết quả cụ thể Sales cần đạt được (VD: Đặt lịch demo giải pháp, gửi tài liệu năng lực...).
- Cách mở đầu: 1-2 câu có thể dùng trực tiếp, lịch sự và gắn liền với tín hiệu/nhu cầu thực tế.
- Thông điệp giá trị: liên hệ nhu cầu/vị trí tuyển dụng với giải pháp hỗ trợ giải quyết bài toán.
- Câu hỏi khám phá: 3-5 câu xác minh hiện trạng công nghệ, tiến độ dự án, ngân sách và người quyết định.
- Bước tiếp theo: một CTA cụ thể, lịch sự và khả thi.
- Điều cần tránh: các dữ liệu còn thiếu hoặc không được phép dùng như fact.

NGUYÊN TẮC
- Không viết lời quảng cáo chung chung.
- Không bịa tên người, chức danh, ngân sách, sản phẩm, giá, cam kết, kinh nghiệm triển khai hoặc mối quan hệ với tổ chức.
- Nếu thiếu email, số điện thoại hoặc người liên hệ, phải hướng dẫn Sales xác minh đầu mối thay vì tự tạo thông tin.
- Ưu tiên câu chữ ngắn, tôn trọng bối cảnh cơ quan/doanh nghiệp Việt Nam."""


PROMPT_DEFINITIONS: dict[str, dict[str, str]] = {
    "scoring": {"setting_key": SCORING_PROMPT_SETTING_KEY, "default_prompt": DEFAULT_SCORING_PROMPT},
    "sales": {"setting_key": SALES_PROMPT_SETTING_KEY, "default_prompt": DEFAULT_SALES_PROMPT},
}


class ScoringPromptService:
    def __init__(self, sheets=None) -> None:
        self.sheets = sheets if sheets is not None else setting_service
        self._cached_prompts: dict[str, str] = {}

    @staticmethod
    def _definition(prompt_type: str) -> dict[str, str]:
        definition = PROMPT_DEFINITIONS.get(str(prompt_type).strip().lower())
        if definition is None:
            raise ValueError("Loại prompt phải là scoring hoặc sales")
        return definition

    @staticmethod
    def _validate(prompt: str) -> str:
        value = str(prompt or "").strip()
        if len(value) < 100:
            raise ValueError("Prompt cần ít nhất 100 ký tự để mô tả đủ yêu cầu")
        if len(value) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt không được vượt quá {MAX_PROMPT_LENGTH:,} ký tự")
        return value

    def get_config(self, prompt_type: PromptType, refresh: bool = False) -> dict[str, Any]:
        normalized_type = str(prompt_type).strip().lower()
        definition = self._definition(normalized_type)
        default_prompt = definition["default_prompt"]
        setting_key = definition["setting_key"]

        if normalized_type in self._cached_prompts and not refresh:
            prompt = self._cached_prompts[normalized_type]
        else:
            stored = self.sheets.load_setting(setting_key)
            raw_prompt = stored.get("prompt") if isinstance(stored, dict) else None
            try:
                prompt = self._validate(raw_prompt) if raw_prompt else default_prompt
            except ValueError:
                prompt = default_prompt
            if raw_prompt is None:
                if not hasattr(self.sheets, "configured") or self.sheets.configured:
                    self.sheets.save_setting(
                        setting_key,
                        {"prompt": default_prompt, "updated_at": utc_now().isoformat()},
                    )
            self._cached_prompts[normalized_type] = prompt

        return {
            "prompt_type": normalized_type,
            "prompt": prompt,
            "default_prompt": default_prompt,
            "is_default": prompt == default_prompt,
            "setting_key": setting_key,
            "storage": "sqlite" if self.sheets is setting_service else ("google_sheets" if getattr(self.sheets, "configured", False) else "default"),
        }

    def get_prompt(self, prompt_type: PromptType) -> str:
        return str(self.get_config(prompt_type)["prompt"])

    def update_prompt(self, prompt_type: PromptType, prompt: str) -> dict[str, Any]:
        normalized_type = str(prompt_type).strip().lower()
        definition = self._definition(normalized_type)
        value = self._validate(prompt)
        if hasattr(self.sheets, "configured") and not self.sheets.configured:
            raise RuntimeError("Kho lưu trữ chưa được cấu hình để lưu prompt")
        payload = {"prompt": value, "updated_at": utc_now().isoformat()}
        res = self.sheets.save_setting(definition["setting_key"], payload)
        if res is False:
            raise RuntimeError(
                getattr(self.sheets, "last_error", None) or "Không thể lưu prompt vào cơ sở dữ liệu"
            )
        self._cached_prompts[normalized_type] = value
        return self.get_config(normalized_type)

    def build_runtime_prompt(
        self,
        *,
        title: str,
        need_summary: str | None,
        need_categories: list[str],
        budget_value: float | None,
        location: str | None,
        contact_email: str | None,
        contact_phone: str | None,
        deadline: datetime.datetime | None,
        published_at: datetime.datetime | None,
        relevance: float,
        evidence: list[str],
        matched_keywords: list[str] | None = None,
    ) -> str:
        now_str = utc_now().strftime("%Y-%m-%d")
        published = published_at.strftime("%Y-%m-%d") if published_at else "Chưa rõ"
        deadline_value = deadline.strftime("%Y-%m-%d") if deadline else "Chưa rõ"
        budget = f"{budget_value:,.0f} VNĐ" if budget_value is not None else "Chưa xác định"
        safe_evidence = []
        for item in (evidence or []):
            text_item = str(item).strip()
            if not text_item:
                continue
            if len(text_item) > 500:
                text_item = text_item[:500] + "..."
            safe_evidence.append(text_item)
            if len(safe_evidence) >= 10:
                break
        evidence_text = "\n".join(f"- {item}" for item in safe_evidence) or "- Không có minh chứng chi tiết"
        matched_keywords_text = ", ".join(
            str(item).strip() for item in (matched_keywords or []) if str(item).strip()
        ) or "Không có keyword khớp được ghi nhận"

        return f"""=== PROMPT CHẤM ĐIỂM DO NGƯỜI DÙNG CẤU HÌNH ===
{self.get_prompt("scoring")}

=== PROMPT KỊCH BẢN SALES DO NGƯỜI DÙNG CẤU HÌNH ===
{self.get_prompt("sales")}

=== DỮ LIỆU CƠ HỘI ===
- Tiêu đề: {title}
- Nhu cầu: {need_summary or "Chưa có tóm tắt"}
- Nhóm nhu cầu: {", ".join(need_categories) or "Chưa phân loại"}
- Ngân sách: {budget}
- Địa bàn: {location or "Chưa xác định"}
- Email công khai: {contact_email or "Không có"}
- Số điện thoại công khai: {contact_phone or "Không có"}
- Ngày đăng: {published}
- Hạn chót: {deadline_value}
- Ngày đánh giá: {now_str}
- Mức độ phù hợp vòng 1: {relevance}
- Keyword khớp ở vòng lọc: {matched_keywords_text}
- Minh chứng:
{evidence_text}

=== RÀNG BUỘC BẮT BUỘC ===
- Kiểm tra CỔNG LIÊN QUAN trước khi cộng bất kỳ điểm nào. Keyword khớp chỉ là tín hiệu đầu vào, không phải bằng chứng đủ; phải có ngữ cảnh nhu cầu/dự án thực tế.
- Nếu không qua CỔNG LIÊN QUAN, total_score phải bằng 0 và recommended_action phải là "NURTURE", bất kể ngân sách, thời hạn hay thông tin liên hệ.
- Áp dụng riêng prompt chấm điểm cho total_score, recommended_action, score_reasons và breakdown.
- Áp dụng riêng prompt Sales cho sales_strategy_suggestion.
- Không sử dụng kiến thức ngoài dữ liệu được cung cấp và không thêm fact không có minh chứng.
- Nếu thiếu email, số điện thoại, ngân sách, deadline hoặc người liên hệ thì nói rõ chưa xác định.
- Trả về duy nhất một JSON object hợp lệ, không markdown và không văn bản ngoài JSON.

JSON BẮT BUỘC:
{{
  "total_score": 0,
  "recommended_action": "CALL|EMAIL|NURTURE",
  "score_reasons": ["lý do dựa trên dữ liệu"],
  "breakdown": [
    {{"rule_name": "tên tiêu chí", "points": 0, "reason": "lý do có bằng chứng"}}
  ],
  "sales_strategy_suggestion": "kịch bản tiếp cận chi tiết bằng tiếng Việt"
}}"""


scoring_prompt_service = ScoringPromptService()

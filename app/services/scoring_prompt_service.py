"""Google Sheets-backed Gemini prompt configuration for scoring and Sales."""

from __future__ import annotations

import datetime
from typing import Any, Literal

from app.pipeline.normalize import utc_now
from app.services.google_sheets_service import google_sheets_service


PromptType = Literal["scoring", "sales"]
SCORING_PROMPT_SETTING_KEY = "gemini_scoring_prompt"
SALES_PROMPT_SETTING_KEY = "gemini_sales_prompt"
MAX_PROMPT_LENGTH = 30_000

DEFAULT_SCORING_PROMPT = """Bạn là chuyên gia đánh giá cơ hội B2B/B2G tại Việt Nam.

NHIỆM VỤ CHẤM ĐIỂM
1. Đánh giá cơ hội từ 0 đến 100, chỉ dựa trên dữ liệu và minh chứng được cung cấp.
2. Tự chọn hành động CALL, EMAIL hoặc NURTURE.
3. Giải thích từng thành phần điểm ngắn gọn, có thể kiểm tra được.

TIÊU CHÍ MẶC ĐỊNH
- Nhu cầu và mức độ phù hợp giải pháp: tối đa 25 điểm.
- Ý định mua sắm, triển khai, thuê dịch vụ hoặc thực hiện dự án: tối đa 20 điểm.
- Ngân sách và khả năng chi trả có bằng chứng: tối đa 20 điểm.
- Thời điểm, hạn chót và độ mới của tín hiệu: tối đa 15 điểm.
- Mức độ phù hợp của tổ chức và địa bàn: tối đa 10 điểm.
- Chất lượng đầu mối liên hệ công khai: tối đa 10 điểm.

NGUYÊN TẮC
- Chỉ cộng điểm cho fact xuất hiện trong dữ liệu hoặc minh chứng.
- Không coi ngân sách, deadline, người liên hệ hay kế hoạch là fact nếu nguồn không nêu rõ.
- Nội dung chỉ bàn luận chung về AI/CNTT nhưng không có dự án, kế hoạch hoặc hành động cụ thể phải có điểm thấp.
- Tín hiệu mới, còn thời hạn và có đầu mối rõ được ưu tiên.
- CALL chỉ phù hợp khi tín hiệu đủ mạnh và có khả năng tiếp cận trực tiếp; EMAIL phù hợp khi cần gửi hồ sơ/tài liệu; NURTURE dành cho tín hiệu còn sớm hoặc thiếu dữ liệu.
- Không tự sửa điểm để khớp một ngưỡng cố định; lựa chọn hành động phải dựa trên toàn bộ bối cảnh."""

DEFAULT_SALES_PROMPT = """Bạn là chuyên gia xây dựng kịch bản tiếp cận Sales B2B/B2G tại Việt Nam.

NHIỆM VỤ
Viết một kịch bản cụ thể, tự nhiên và có thể sử dụng ngay cho cơ hội được cung cấp. Kịch bản phải phù hợp với hành động CALL, EMAIL hoặc NURTURE do Gemini đánh giá.

CẤU TRÚC BẮT BUỘC
Mỗi mục phải nằm trên dòng riêng:
- Đối tượng nên tiếp cận: vai trò hoặc phòng ban phù hợp; nếu chưa biết người cụ thể thì không tự đặt tên.
- Kênh ưu tiên: điện thoại, email hoặc nuôi dưỡng, kèm lý do ngắn.
- Mục tiêu tiếp cận: kết quả cụ thể Sales cần đạt được.
- Cách mở đầu: 1-2 câu có thể dùng trực tiếp, không khẳng định điều chưa có bằng chứng.
- Thông điệp giá trị: liên hệ nhu cầu thực tế với nhóm giải pháp phù hợp.
- Câu hỏi khám phá: 3-5 câu xác minh hiện trạng, phạm vi, ngân sách, tiến độ và người quyết định.
- Bước tiếp theo: một CTA cụ thể, lịch sự và khả thi.
- Điều cần tránh: các dữ liệu còn thiếu hoặc không được phép dùng như fact.

NGUYÊN TẮC
- Không viết lời quảng cáo chung chung.
- Không bịa tên người, chức danh, ngân sách, sản phẩm, giá, cam kết, kinh nghiệm triển khai hoặc mối quan hệ với tổ chức.
- Nếu thiếu email, số điện thoại hoặc người liên hệ, phải hướng dẫn Sales xác minh đầu mối thay vì tự tạo thông tin.
- Không nói rằng tổ chức đã quyết định mua nếu minh chứng chỉ thể hiện kế hoạch, đề xuất hoặc nhu cầu sơ bộ.
- Ưu tiên câu chữ ngắn, tôn trọng bối cảnh cơ quan/doanh nghiệp Việt Nam."""


PROMPT_DEFINITIONS: dict[str, dict[str, str]] = {
    "scoring": {"setting_key": SCORING_PROMPT_SETTING_KEY, "default_prompt": DEFAULT_SCORING_PROMPT},
    "sales": {"setting_key": SALES_PROMPT_SETTING_KEY, "default_prompt": DEFAULT_SALES_PROMPT},
}


class ScoringPromptService:
    def __init__(self, sheets=google_sheets_service) -> None:
        self.sheets = sheets
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
            if raw_prompt is None and self.sheets.configured:
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
            "storage": "google_sheets" if self.sheets.configured else "default",
        }

    def get_prompt(self, prompt_type: PromptType) -> str:
        return str(self.get_config(prompt_type)["prompt"])

    def update_prompt(self, prompt_type: PromptType, prompt: str) -> dict[str, Any]:
        normalized_type = str(prompt_type).strip().lower()
        definition = self._definition(normalized_type)
        value = self._validate(prompt)
        if not self.sheets.configured:
            raise RuntimeError("Google Sheets chưa được cấu hình để lưu prompt")
        payload = {"prompt": value, "updated_at": utc_now().isoformat()}
        if not self.sheets.save_setting(definition["setting_key"], payload):
            raise RuntimeError(
                self.sheets.last_error or "Không thể lưu prompt vào worksheet Settings"
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
    ) -> str:
        now_str = utc_now().strftime("%Y-%m-%d")
        published = published_at.strftime("%Y-%m-%d") if published_at else "Chưa rõ"
        deadline_value = deadline.strftime("%Y-%m-%d") if deadline else "Chưa rõ"
        budget = f"{budget_value:,.0f} VNĐ" if budget_value is not None else "Chưa xác định"
        evidence_text = "\n".join(
            f"- {item}" for item in evidence[:8] if str(item).strip()
        ) or "- Không có minh chứng chi tiết"

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
- Minh chứng:
{evidence_text}

=== RÀNG BUỘC BẮT BUỘC ===
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

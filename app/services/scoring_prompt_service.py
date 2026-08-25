"""Google Sheets-backed Gemini scoring and sales-script prompt configuration."""

from __future__ import annotations

import datetime
from typing import Any

from app.pipeline.normalize import utc_now
from app.services.google_sheets_service import google_sheets_service


SCORING_PROMPT_SETTING_KEY = "gemini_scoring_sales_prompt"
MAX_SCORING_PROMPT_LENGTH = 30_000

DEFAULT_SCORING_PROMPT = """Bạn là chuyên gia đánh giá cơ hội B2B/B2G và xây dựng kịch bản tiếp cận Sales tại Việt Nam.

NHIỆM VỤ
1. Đánh giá cơ hội từ 0 đến 100 dựa trên bằng chứng được cung cấp.
2. Chọn đúng hành động CALL, EMAIL hoặc NURTURE.
3. Viết một kịch bản tiếp cận đủ cụ thể để Sales có thể sử dụng ngay.

TIÊU CHÍ CHẤM ĐIỂM MẶC ĐỊNH
- Nhu cầu và mức độ phù hợp giải pháp: tối đa 25 điểm.
- Ý định mua sắm, triển khai, thuê dịch vụ hoặc thực hiện dự án: tối đa 20 điểm.
- Ngân sách và khả năng chi trả có bằng chứng: tối đa 20 điểm.
- Thời điểm, hạn chót và độ mới của tín hiệu: tối đa 15 điểm.
- Mức độ phù hợp của tổ chức và địa bàn: tối đa 10 điểm.
- Chất lượng đầu mối liên hệ công khai: tối đa 10 điểm.

NGUYÊN TẮC ĐÁNH GIÁ
- Chỉ cộng điểm cho thông tin xuất hiện trong dữ liệu và minh chứng.
- Không coi ngân sách, deadline, người liên hệ hoặc kế hoạch là fact nếu dữ liệu không nêu rõ.
- Tin chỉ bàn luận chung về AI/CNTT nhưng không có nhu cầu, dự án, kế hoạch hoặc hành động cụ thể phải có điểm thấp.
- Tín hiệu mới, còn thời hạn và có đầu mối rõ được ưu tiên hơn tín hiệu cũ hoặc mơ hồ.
- Tự chọn CALL, EMAIL hoặc NURTURE dựa trên toàn bộ bối cảnh; giải thích ngắn gọn trong score_reasons.

YÊU CẦU CHO KỊCH BẢN SALES
Kịch bản phải viết bằng tiếng Việt tự nhiên, thực tế và bám sát dữ liệu. Nội dung sales_strategy_suggestion cần có các phần trên dòng riêng:
- Đối tượng nên tiếp cận: vai trò hoặc phòng ban phù hợp; nếu chưa biết người cụ thể thì không tự đặt tên.
- Kênh ưu tiên: điện thoại, email hoặc nuôi dưỡng, kèm lý do ngắn.
- Mục tiêu cuộc tiếp cận: kết quả cụ thể Sales cần đạt được.
- Cách mở đầu: 1-2 câu có thể sử dụng trực tiếp, không khẳng định điều chưa có bằng chứng.
- Thông điệp giá trị: liên hệ nhu cầu thực tế với nhóm giải pháp phù hợp; không tự tạo tên sản phẩm, giá hoặc cam kết.
- Câu hỏi khám phá: 3-5 câu để xác minh hiện trạng, phạm vi, ngân sách, tiến độ và người quyết định.
- Bước tiếp theo đề xuất: một CTA cụ thể, lịch sự và có khả năng thực hiện.
- Điều cần tránh: nêu rõ dữ liệu nào còn thiếu hoặc không nên dùng như một fact.

Không viết lời quảng cáo chung chung. Không bịa tên người, chức danh, ngân sách, sản phẩm, kinh nghiệm triển khai hoặc mối quan hệ với tổ chức."""


class ScoringPromptService:
    def __init__(self, sheets=google_sheets_service) -> None:
        self.sheets = sheets
        self._cached_prompt: str | None = None

    @staticmethod
    def _validate(prompt: str) -> str:
        value = str(prompt or "").strip()
        if len(value) < 100:
            raise ValueError("Prompt cần ít nhất 100 ký tự để mô tả đủ tiêu chí")
        if len(value) > MAX_SCORING_PROMPT_LENGTH:
            raise ValueError(
                f"Prompt không được vượt quá {MAX_SCORING_PROMPT_LENGTH:,} ký tự"
            )
        return value

    def get_config(self, refresh: bool = False) -> dict[str, Any]:
        if self._cached_prompt is not None and not refresh:
            prompt = self._cached_prompt
            return {
                "prompt": prompt,
                "default_prompt": DEFAULT_SCORING_PROMPT,
                "is_default": prompt == DEFAULT_SCORING_PROMPT,
                "storage": "google_sheets" if self.sheets.configured else "default",
            }

        stored = self.sheets.load_setting(SCORING_PROMPT_SETTING_KEY)
        raw_prompt = stored.get("prompt") if isinstance(stored, dict) else None
        try:
            prompt = self._validate(raw_prompt) if raw_prompt else DEFAULT_SCORING_PROMPT
        except ValueError:
            prompt = DEFAULT_SCORING_PROMPT

        if raw_prompt is None and self.sheets.configured:
            self.sheets.save_setting(
                SCORING_PROMPT_SETTING_KEY,
                {
                    "prompt": DEFAULT_SCORING_PROMPT,
                    "updated_at": utc_now().isoformat(),
                },
            )
        self._cached_prompt = prompt
        return {
            "prompt": prompt,
            "default_prompt": DEFAULT_SCORING_PROMPT,
            "is_default": prompt == DEFAULT_SCORING_PROMPT,
            "storage": "google_sheets" if self.sheets.configured else "default",
        }

    def get_prompt(self) -> str:
        return str(self.get_config()["prompt"])

    def update_prompt(self, prompt: str) -> dict[str, Any]:
        value = self._validate(prompt)
        if not self.sheets.configured:
            raise RuntimeError("Google Sheets chưa được cấu hình để lưu prompt")
        payload = {"prompt": value, "updated_at": utc_now().isoformat()}
        if not self.sheets.save_setting(SCORING_PROMPT_SETTING_KEY, payload):
            raise RuntimeError(
                self.sheets.last_error or "Không thể lưu prompt vào worksheet Settings"
            )
        self._cached_prompt = value
        return self.get_config()

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

        return f"""=== CHỈ DẪN DO NGƯỜI DÙNG CẤU HÌNH ===
{self.get_prompt()}

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
- Toàn bộ điểm số, hành động và kịch bản do bạn tự đánh giá từ dữ liệu trên.
- Không sử dụng kiến thức ngoài prompt. Không thêm fact không có trong dữ liệu hoặc minh chứng.
- Nếu thiếu email, số điện thoại, ngân sách, deadline hoặc người liên hệ thì phải nói rõ là chưa xác định; không tự suy diễn.
- sales_strategy_suggestion phải là kịch bản chi tiết theo đúng cấu trúc người dùng yêu cầu, không phải một câu nhận xét chung.
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

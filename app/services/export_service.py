from __future__ import annotations

import csv
import io
import json
from typing import List
from app.models.lead import Lead


class ExportService:
    """Service to export Leads to CSV and JSON formats."""

    @staticmethod
    def export_to_csv(leads: List[Lead]) -> str:
        """
        Generate CSV string with UTF-8-BOM encoding for full Vietnamese support in Excel.
        """
        output = io.StringIO()
        # Write UTF-8 BOM
        output.write("\ufeff")

        writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)
        # Header matching Phụ lục C of plan
        writer.writerow([
            "Lead ID",
            "Điểm số (Score)",
            "Hành động đề xuất (Action)",
            "Đơn vị / Cơ quan (Organization)",
            "Nhu cầu trọng tâm (Need Summary)",
            "Phân loại (Categories)",
            "Ngân sách (Budget VND)",
            "Ngân sách text",
            "Địa bàn (Location)",
            "Nguồn (Source)",
            "Link nguồn (Source URL)",
            "Ngày đăng (Published Date)",
            "Ngày crawl (Crawled Date)",
            "Người liên hệ",
            "Email",
            "Số điện thoại",
            "Lý do chấm điểm (Score Reasons)",
        ])

        for lead in leads:
            categories_str = ", ".join(lead.need_categories or [])
            reasons_str = " | ".join(lead.score_reasons or [])
            writer.writerow([
                lead.id,
                lead.score,
                lead.recommended_action,
                lead.organization_name or "",
                lead.need_summary or "",
                categories_str,
                lead.budget_value or "",
                lead.budget_text or "",
                lead.location or "",
                lead.source,
                lead.source_url,
                lead.published_at.strftime("%d/%m/%Y %H:%M") if lead.published_at else "",
                lead.crawled_at.strftime("%d/%m/%Y %H:%M") if lead.crawled_at else "",
                lead.contact_name or "",
                lead.contact_email or "",
                lead.contact_phone or "",
                reasons_str,
            ])

        return output.getvalue()

    @staticmethod
    def export_to_json(leads: List[Lead]) -> str:
        data = []
        for lead in leads:
            data.append({
                "id": lead.id,
                "score": lead.score,
                "recommended_action": lead.recommended_action,
                "organization_name": lead.organization_name,
                "organization_type": lead.organization_type,
                "need_summary": lead.need_summary,
                "need_categories": lead.need_categories,
                "budget_value": lead.budget_value,
                "budget_text": lead.budget_text,
                "location": lead.location,
                "source": lead.source,
                "source_url": lead.source_url,
                "published_at": lead.published_at.isoformat() if lead.published_at else None,
                "crawled_at": lead.crawled_at.isoformat() if lead.crawled_at else None,
                "contact_name": lead.contact_name,
                "contact_email": lead.contact_email,
                "contact_phone": lead.contact_phone,
                "deadline": lead.deadline.isoformat() if lead.deadline else None,
                "relevance": lead.relevance,
                "score_reasons": lead.score_reasons,
                "evidence": lead.evidence,
                "status": lead.status,
            })
        return json.dumps(data, ensure_ascii=False, indent=2)


export_service = ExportService()

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, asc, func, or_
from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadFilterParams, LeadStatusEnum, ActionEnum
from app.pipeline.normalize import utc_now


class LeadService:
    """Service layer for querying, filtering, and updating leads."""

    @staticmethod
    def get_leads(db: Session, params: LeadFilterParams) -> Tuple[List[Lead], int]:
        query = db.query(Lead)

        # 1. Filter by Source
        if params.source:
            query = query.filter(Lead.source == params.source)

        # 2. Filter by Action
        if params.action:
            query = query.filter(Lead.recommended_action == params.action.value)

        # 3. Filter by Status
        if params.status:
            query = query.filter(Lead.status == params.status.value)
        elif not params.include_archived:
            query = query.filter(Lead.status != LeadStatusEnum.ARCHIVED.value)

        # 4. Score filters are only applied when explicitly requested.
        if params.min_score is not None:
            query = query.filter(Lead.score >= params.min_score)
        if params.max_score is not None:
            query = query.filter(Lead.score <= params.max_score)

        # 5. Filter by Location
        if params.location:
            query = query.filter(Lead.location.ilike(f"%{params.location}%"))

        # 6. Fulltext Search in Title, Org, Need Summary
        if params.query:
            q = f"%{params.query}%"
            query = query.filter(
                or_(
                    Lead.title.ilike(q),
                    Lead.organization_name.ilike(q),
                    Lead.need_summary.ilike(q),
                    Lead.budget_text.ilike(q),
                )
            )

        # Total count
        total = query.count()

        # Sorting
        sort_col = getattr(Lead, params.sort_by, Lead.score)
        if params.sort_order.lower() == "asc":
            query = query.order_by(asc(sort_col))
        else:
            query = query.order_by(desc(sort_col), desc(Lead.crawled_at))

        # Pagination
        offset = (params.page - 1) * params.page_size
        leads = query.offset(offset).limit(params.page_size).all()

        return leads, total

    @staticmethod
    def get_lead_by_id(db: Session, lead_id: str) -> Optional[Lead]:
        return db.query(Lead).filter(Lead.id == lead_id).first()

    @staticmethod
    def update_lead_status(db: Session, lead_id: str, status: LeadStatusEnum, notes: Optional[str] = None) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return None
        lead.status = status.value
        if notes is not None:
            lead.sales_notes = notes
        lead.updated_at = utc_now()
        db.commit()
        db.refresh(lead)
        return lead

    @staticmethod
    def get_dashboard_stats(db: Session) -> Dict[str, Any]:
        # Every non-archived AI-processed lead is visible, regardless of score.
        active_query = db.query(Lead).filter(Lead.status != LeadStatusEnum.ARCHIVED.value)
        total_leads = active_query.count()
        hot_leads = active_query.filter(Lead.recommended_action == "CALL").count()
        qualified_leads = active_query.filter(Lead.recommended_action == "EMAIL").count()
        nurture_leads = active_query.filter(Lead.recommended_action == "NURTURE").count()

        archived_count = db.query(Lead).filter(Lead.status == LeadStatusEnum.ARCHIVED.value).count()

        # Leads crawled today
        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        leads_today = active_query.filter(Lead.crawled_at >= today_start).count()

        # Aggregate only the same visible dataset.
        avg_score_res = active_query.with_entities(func.avg(Lead.score)).scalar() or 0.0
        avg_score = round(float(avg_score_res), 1)

        total_budget_res = active_query.with_entities(func.sum(Lead.budget_value)).scalar() or 0.0

        # Breakdown by Source
        source_counts = (
            db.query(Lead.source, func.count(Lead.id))
            .filter(Lead.status != LeadStatusEnum.ARCHIVED.value)
            .group_by(Lead.source)
            .all()
        )
        sources_breakdown = {s: count for s, count in source_counts}

        # Breakdown by Action
        action_counts = {
            "CALL": hot_leads,
            "EMAIL": qualified_leads,
            "NURTURE": nurture_leads,
        }

        return {
            "total_leads": total_leads,
            "hot_leads": hot_leads,
            "qualified_leads": qualified_leads,
            "nurture_leads": nurture_leads,
            "archived_leads_count": archived_count,
            "leads_today": leads_today,
            "avg_score": avg_score,
            "total_pipeline_budget": total_budget_res,
            "sources_breakdown": sources_breakdown,
            "action_breakdown": action_counts,
        }


lead_service = LeadService()

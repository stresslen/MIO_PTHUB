from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.crawlers import get_adapter, get_all_adapters, SourceAdapter
from app.database import SessionLocal
from app.models.lead import Lead, ActionEnum, LeadStatusEnum
from app.models.source import CrawlRun, CrawlStatusEnum
from app.pipeline.dedup import compute_fingerprint, is_duplicate
from app.pipeline.extract import ai_extractor, prefilter_keywords, AIAuthenticationError, AIQuotaOrAPIError
from app.pipeline.normalize import clean_html, parse_datetime, utc_now
from app.pipeline.scoring import scoring_engine
from app.services.priority_service import priority_coordinator
from app.services.google_sheets_service import google_sheets_service
from app.services.source_service import CUSTOM_MAX_PAGES, source_service
from app.services.company_enrichment_service import company_enrichment_service, CompanyEnrichmentResult

logger = logging.getLogger(__name__)


def publication_or_crawl_time(
    published_at: Optional[datetime.datetime],
    crawled_at: Optional[datetime.datetime] = None,
) -> datetime.datetime:
    """Use the trusted publication timestamp, falling back to crawl time."""
    return published_at or crawled_at or utc_now()


def calculate_since_datetime(
    timeframe: Optional[str],
    now: Optional[datetime.datetime] = None,
) -> Optional[datetime.datetime]:
    """Return a timezone-naive Vietnam-local cutoff for a supported window."""
    if not timeframe:
        return None
    current = now or datetime.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None)
    windows = {
        "1_day": datetime.timedelta(days=1),
        "1_week": datetime.timedelta(days=7),
        "1_month": datetime.timedelta(days=30),
    }
    if timeframe not in windows:
        raise ValueError(f"Khoảng thời gian không hợp lệ: {timeframe}")
    return current - windows[timeframe]


class CrawlerService:
    """
    Crawler Service orchestrating discovery, fetching, extraction, scoring, and persistence.
    Processes live crawled data end-to-end.
    """

    @staticmethod
    def _merge_company_contact(extracted, enrichment: CompanyEnrichmentResult) -> None:
        """Use only source-backed round-two contact/evidence; never synthesize values."""
        contacts = sorted(
            enrichment.contacts,
            key=lambda item: item.get("decision_score") if item.get("decision_score") is not None else -1,
            reverse=True,
        )
        if contacts:
            primary = contacts[0]
            extracted.contact_name = extracted.contact_name or primary.get("full_name")
            extracted.contact_email = extracted.contact_email or primary.get("email")
            extracted.contact_phone = extracted.contact_phone or primary.get("phone")
        evidence = list(extracted.evidence or [])
        for item in enrichment.evidence:
            note = f"{item.get('evidence_text')} — {item.get('source_url')}"
            if note not in evidence:
                evidence.append(note)
        extracted.evidence = evidence

    async def _enrich_company(self, extracted) -> CompanyEnrichmentResult:
        result = await company_enrichment_service.enrich(
            organization_name=extracted.organization_name,
            organization_type=extracted.organization_type,
            organization_website=extracted.organization_website,
            organization_tax_code=extracted.organization_tax_code,
            location=extracted.location,
        )
        self._merge_company_contact(extracted, result)
        return result

    async def _extract_with_priority(self, title: str, content: str, **kwargs):
        return await priority_coordinator.run_blocking(
            ai_extractor.extract,
            title,
            content,
            worker_name="Gemini extraction",
            **kwargs,
        )

    async def _score_with_priority(self, **kwargs):
        return await priority_coordinator.run_blocking(
            scoring_engine.evaluate,
            worker_name="Gemini scoring and sales",
            **kwargs,
        )

    async def run_crawler_for_source(
        self,
        source_id: str,
        db: Optional[Session] = None,
        force_recrawl: bool = False,
        timeframe: Optional[str] = "1_week",
        is_manual_fe: bool = False,
    ) -> CrawlRun:
        """
        Execute end-to-end crawl and pipeline processing for a single source.
        Filters by timeframe: 1_day (24h), 1_week (7d), 1_month (30d), all (None).
        If is_manual_fe=True, executes with HIGHEST PREEMPTIVE PRIORITY.
        """
        if is_manual_fe:
            async with priority_coordinator.fe_priority_context(f"Crawl Source: {source_id}"):
                return await self._run_crawler_for_source_core(source_id, db, force_recrawl, timeframe, is_manual_fe=True)
        else:
            return await self._run_crawler_for_source_core(source_id, db, force_recrawl, timeframe, is_manual_fe=False)

    async def _run_crawler_for_source_core(
        self,
        source_id: str,
        db: Optional[Session] = None,
        force_recrawl: bool = False,
        timeframe: Optional[str] = "1_week",
        is_manual_fe: bool = False,
    ) -> CrawlRun:
        close_db_on_exit = False
        if db is None:
            db = SessionLocal()
            close_db_on_exit = True

        adapter = get_adapter(source_id)
        source_service.record_status(source_id, "RUNNING")

        # Calculate since cutoff datetime
        since = calculate_since_datetime(timeframe)
        now = utc_now()

        # Create CrawlRun record
        crawl_run = CrawlRun(
            source=source_id,
            status=CrawlStatusEnum.RUNNING.value,
            start_time=now,
        )
        db.add(crawl_run)
        db.commit()
        db.refresh(crawl_run)

        try:
            logger.info(f"[{source_id}] Starting live crawl (timeframe={timeframe}, is_manual_fe={is_manual_fe})...")
            if not is_manual_fe:
                await priority_coordinator.yield_if_fe_active(f"Crawl discovery {source_id}")
            # 1. Discover live URLs with timeframe filter
            discovery_limit = CUSTOM_MAX_PAGES if getattr(adapter, "is_generic", False) else None
            discovered_urls = await adapter.discover(since=since, max_items=discovery_limit)
            crawl_run.total_discovered = len(discovered_urls)
            db.commit()
            logger.info(f"[{source_id}] Discovered {len(discovered_urls)} live URLs")

            for url in discovered_urls:
                if not is_manual_fe:
                    await priority_coordinator.yield_if_fe_active(f"Crawl {source_id}")
                try:
                    # 2. Fetch page
                    raw_doc = await adapter.fetch(url)

                    # 3. Parse basic metadata
                    parsed = await adapter.parse(raw_doc)
                    item_crawled_at = utc_now()
                    parsed.published_at = publication_or_crawl_time(
                        parsed.published_at, item_crawled_at
                    )

                    # 3.1. Timeframe check: skip if article is older than since
                    if since and (not parsed.published_at or parsed.published_at < since):
                        logger.info(f"[{source_id}] Skipping {url} (published {parsed.published_at!s} outside {timeframe})")
                        crawl_run.filtered_out += 1
                        continue

                    # 4. Fingerprint & Dedup check
                    fingerprint = compute_fingerprint(url, parsed.title, parsed.published_at)
                    existing = db.query(Lead).filter(or_(Lead.content_fingerprint == fingerprint, Lead.source_url == url)).first()
                    if existing:
                        crawl_run.duplicate_leads += 1
                        logger.info(f"[{source_id}] Duplicate skipped: '{parsed.title[:35]}...'")
                        continue

                    # 5. Custom sites crawl every page; provider keyword feeds were already filtered upstream.
                    if getattr(adapter, "is_generic", False) or getattr(adapter, "is_keyword_feed", False):
                        category = "Nguồn tìm theo từ khóa" if getattr(adapter, "is_keyword_feed", False) else "Website tùy chỉnh"
                        is_rel, matched_kws, matched_cats = True, [], [category]
                    else:
                        is_rel, matched_kws, matched_cats = prefilter_keywords(
                            parsed.title, parsed.raw_content
                        )
                    if not is_rel:
                        logger.info(f"[{source_id}] Filtered out (No matching AI/CĐS/Procurement keywords): '{parsed.title[:40]}...'")
                        crawl_run.filtered_out += 1
                        continue

                    # 6. AI Extraction is mandatory; failures never create a lead.
                    extracted = await self._extract_with_priority(
                        parsed.title,
                        parsed.raw_content,
                        source=source_id,
                        raise_on_api_error=True,
                    )
                    enrichment = await self._enrich_company(extracted)

                    # Merge only categories actually found by keyword matching or AI.
                    combined_categories = list(set(matched_cats + extracted.need_categories))

                    # Deadline parsing
                    deadline_dt = parse_datetime(extracted.deadline) if extracted.deadline else None

                    # 7. Lead Scoring (AI / Rule-based)
                    score_res = await self._score_with_priority(
                        title=parsed.title,
                        need_summary=extracted.need_summary,
                        need_categories=combined_categories,
                        budget_value=extracted.budget_value,
                        location=extracted.location,
                        contact_email=extracted.contact_email,
                        contact_phone=extracted.contact_phone,
                        deadline=deadline_dt,
                        published_at=parsed.published_at,
                        relevance=extracted.relevance,
                        raw_evidence=extracted.evidence,
                    )

                    # 8. Persist every keyword-related item successfully processed by AI.
                    lead = Lead(
                        source=source_id,
                        source_url=url,
                        title=parsed.title,
                        published_at=parsed.published_at,
                        crawled_at=item_crawled_at,
                        organization_name=extracted.organization_name,
                        organization_type=extracted.organization_type or "other",
                        need_summary=extracted.need_summary,
                        need_categories=combined_categories,
                        budget_value=extracted.budget_value,
                        budget_text=extracted.budget_text,
                        location=extracted.location,
                        contact_name=extracted.contact_name,
                        contact_email=extracted.contact_email,
                        contact_phone=extracted.contact_phone,
                        deadline=deadline_dt,
                        keywords_matched=matched_kws,
                        relevance=extracted.relevance,
                        score=score_res.total_score,
                        recommended_action=score_res.recommended_action,
                        score_reasons=score_res.reasons,
                        evidence=extracted.evidence,
                        sales_strategy=score_res.sales_strategy_suggestion,
                        raw_content_ref=raw_doc.snapshot_path,
                        content_fingerprint=fingerprint,
                        status="NEW",
                        enrichment_status=enrichment.status,
                        enrichment_message=enrichment.message,
                    )
                    db.add(lead)
                    db.flush()
                    organization = company_enrichment_service.persist(db, lead, enrichment)
                    crawl_run.new_leads += 1
                    db.commit()
                    db.refresh(lead)
                    await priority_coordinator.run_blocking(
                        google_sheets_service.upsert_lead,
                        lead,
                        worker_name="Google Sheets lead upsert",
                    )
                    if organization is not None:
                        await priority_coordinator.run_blocking(
                            google_sheets_service.upsert_organization_profile,
                            organization.id,
                            worker_name="Google Sheets organization upsert",
                        )
                    logger.info(f"[{source_id}] ✅ Đã lưu bài liên quan sau AI: '{parsed.title[:40]}...' (Score: {score_res.total_score} - {score_res.recommended_action})")

                except AIAuthenticationError as auth_err:
                    db.rollback()
                    crawl_run.error_count += 1
                    crawl_run.status = CrawlStatusEnum.PARTIAL.value
                    crawl_run.error_message = f"AI authentication failed: {auth_err}"
                    logger.error(
                        "[%s] AI authentication failed; stopping without saving unprocessed data: %s",
                        source_id,
                        auth_err,
                    )
                    break
                except AIQuotaOrAPIError as quota_err:
                    db.rollback()
                    logger.warning(f"[{source_id}] ⚠️ Gemini API Quota/Error for {url}: {quota_err}")
                    if timeframe == "1_month":
                        logger.warning(f"[{source_id}] 🛑 Chế độ crawl 1 tháng: Dừng cào để bảo toàn dữ liệu và hạn ngạch.")
                        crawl_run.status = CrawlStatusEnum.PARTIAL.value
                        crawl_run.error_message = f"Dừng do hạn ngạch API: {quota_err}"
                        crawl_run.end_time = utc_now()
                        try:
                            db.commit()
                        except Exception:
                            db.rollback()
                        break  # Stop 1-month crawl immediately!
                    else:
                        crawl_run.error_count += 1
                        logger.warning(
                            "[%s] AI unavailable; skipped unprocessed item and will retry on a later crawl: %s",
                            source_id,
                            url,
                        )


                except Exception as item_err:
                    db.rollback()
                    logger.warning(f"[{source_id}] Error processing item {url}: {item_err}")
                    crawl_run.error_count += 1
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()

            crawl_run.status = CrawlStatusEnum.SUCCESS.value if crawl_run.error_count == 0 else CrawlStatusEnum.PARTIAL.value
            crawl_run.end_time = utc_now()
            try:
                db.commit()
            except Exception:
                db.rollback()
            source_service.record_status(
                source_id,
                crawl_run.status,
                None if crawl_run.error_count == 0 else (crawl_run.error_message or f"{crawl_run.error_count} trang lỗi"),
            )
            logger.info(f"[{source_id}] Finished crawl run {crawl_run.id}: {crawl_run.new_leads} new leads")

        except Exception as e:
            db.rollback()
            logger.error(f"[{source_id}] Fatal crawl run error: {e}", exc_info=True)
            crawl_run.status = CrawlStatusEnum.FAILED.value
            crawl_run.error_message = str(e)
            crawl_run.end_time = utc_now()
            try:
                db.commit()
            except Exception:
                db.rollback()
            source_service.record_status(source_id, "FAILED", e)

        finally:
            if close_db_on_exit:
                db.close()

        return crawl_run

    async def process_pending_queue(self, db: Session) -> int:
        """Process leads stuck in PENDING_AI status when API quota is restored."""
        # Yield to any active Frontend requests first
        await priority_coordinator.yield_if_fe_active("Pending Queue Worker")
        
        pending_leads = db.query(Lead).filter(Lead.status == LeadStatusEnum.PENDING_AI.value).all()
        if not pending_leads:
            return 0

        logger.info(f"[QueueWorker] Đang xử lý {len(pending_leads)} bài viết trong hàng đợi PENDING_AI...")
        processed_count = 0

        for lead in pending_leads:
            await priority_coordinator.yield_if_fe_active("Pending Queue Worker")
            try:
                content = ""
                if lead.raw_content_ref and Path(lead.raw_content_ref).exists():
                    with open(lead.raw_content_ref, "r", encoding="utf-8", errors="ignore") as fp:
                        content = clean_html(fp.read())

                if not content:
                    content = lead.title

                extracted = await self._extract_with_priority(lead.title, content, source=lead.source, raise_on_api_error=True)
                enrichment = await self._enrich_company(extracted)
                combined_cats = list(set((lead.need_categories or []) + extracted.need_categories))

                deadline_dt = parse_datetime(extracted.deadline) if extracted.deadline else None
                score_res = await self._score_with_priority(
                    title=lead.title,
                    need_summary=extracted.need_summary,
                    need_categories=combined_cats,
                    budget_value=extracted.budget_value,
                    location=extracted.location,
                    contact_email=extracted.contact_email,
                    contact_phone=extracted.contact_phone,
                    deadline=deadline_dt,
                    published_at=lead.published_at,
                    relevance=extracted.relevance,
                    raw_evidence=extracted.evidence,
                )

                lead.organization_type = extracted.organization_type or "other"
                lead.organization_name = extracted.organization_name
                lead.organization_type = extracted.organization_type or lead.organization_type
                lead.need_summary = extracted.need_summary
                lead.need_categories = combined_cats
                lead.budget_value = extracted.budget_value
                lead.budget_text = extracted.budget_text
                lead.location = extracted.location
                lead.contact_name = extracted.contact_name
                lead.contact_email = extracted.contact_email
                lead.contact_phone = extracted.contact_phone
                lead.deadline = deadline_dt
                lead.relevance = extracted.relevance
                lead.score = score_res.total_score
                lead.recommended_action = score_res.recommended_action
                lead.score_reasons = score_res.reasons
                lead.evidence = extracted.evidence
                lead.sales_strategy = score_res.sales_strategy_suggestion
                lead.status = LeadStatusEnum.NEW.value
                lead.updated_at = utc_now()
                organization = company_enrichment_service.persist(db, lead, enrichment)
                db.commit()
                db.refresh(lead)
                await priority_coordinator.run_blocking(
                    google_sheets_service.upsert_lead,
                    lead,
                    worker_name="Google Sheets lead upsert",
                )
                if organization is not None:
                    await priority_coordinator.run_blocking(
                        google_sheets_service.upsert_organization_profile,
                        organization.id,
                        worker_name="Google Sheets organization upsert",
                    )
                processed_count += 1
                logger.info(f"[QueueWorker] ✅ Đã xử lý xong bài liên quan trong hàng đợi: '{lead.title[:40]}' (Score: {score_res.total_score})")

            except AIQuotaOrAPIError as q_err:
                logger.warning(f"[QueueWorker] Hạn mức API chưa mở lại: {q_err}. Tạm dừng xử lý hàng đợi.")
                break
            except Exception as e:
                db.rollback()
                logger.warning(f"[QueueWorker] Lỗi xử lý hàng đợi {lead.id}: {e}")

        return processed_count

    async def run_all_sources(
        self,
        force_recrawl: bool = False,
        timeframe: Optional[str] = "1_month",
        batch_size: int = 25,
        is_manual_fe: bool = False,
    ) -> List[CrawlRun]:
        """
        Round-Robin Interleaved Multi-Source Crawling:
        If is_manual_fe=True, executes with HIGHEST PREEMPTIVE PRIORITY over background tasks.
        """
        if is_manual_fe:
            async with priority_coordinator.fe_priority_context(f"Crawl All Sources ({timeframe})"):
                return await self._run_all_sources_core(force_recrawl, timeframe, batch_size, is_manual_fe=True)
        else:
            return await self._run_all_sources_core(force_recrawl, timeframe, batch_size, is_manual_fe=False)

    async def _run_all_sources_core(
        self,
        force_recrawl: bool = False,
        timeframe: Optional[str] = "1_month",
        batch_size: int = 25,
        is_manual_fe: bool = False,
    ) -> List[CrawlRun]:
        logger.info(f"[RoundRobin] 🚀 Bắt đầu crawl xoay vòng đa nguồn (Batch: {batch_size} bài/nguồn, Timeframe: {timeframe}, is_manual_fe={is_manual_fe})...")
        adapters = get_all_adapters(scheduled_only=not is_manual_fe)
        if not adapters:
            return []

        since = calculate_since_datetime(timeframe)
        db = SessionLocal()
        
        # 1. Initialize CrawlRun records & Discover candidate URLs for each source
        crawl_runs: Dict[str, CrawlRun] = {}
        discovered_map: Dict[str, List[str]] = {}
        index_map: Dict[str, int] = {}

        for source_id, adapter in adapters.items():
            if not is_manual_fe:
                await priority_coordinator.yield_if_fe_active("Daily Scheduler Discovery")
            run = CrawlRun(
                source=source_id,
                start_time=utc_now(),
                status=CrawlStatusEnum.RUNNING.value,
                total_discovered=0,
                new_leads=0,
                duplicate_leads=0,
                filtered_out=0,
                error_count=0,
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            crawl_runs[source_id] = run
            index_map[source_id] = 0
            source_service.record_status(source_id, "RUNNING")

            # Discover URLs for this source
            try:
                discovery_limit = CUSTOM_MAX_PAGES if getattr(adapter, "is_generic", False) else None
                urls = await adapter.discover(since=since, max_items=discovery_limit)
                discovered_map[source_id] = urls
                run.total_discovered = len(urls)
                db.commit()
                logger.info(f"[{source_id}] Discovered {len(urls)} URLs for {timeframe}")
            except Exception as disc_err:
                logger.error(f"[{source_id}] Discovery failed: {disc_err}")
                discovered_map[source_id] = []
                run.status = CrawlStatusEnum.FAILED.value
                run.error_message = str(disc_err)
                db.commit()
                source_service.record_status(source_id, "FAILED", disc_err)

        # 2. Round-Robin Batch Execution Loop (interleaved across enabled sources)
        round_num = 1
        stop_all = False

        while not stop_all:
            if not is_manual_fe:
                await priority_coordinator.yield_if_fe_active(f"Daily Scheduler Round {round_num}")
            active_in_this_round = 0
            logger.info(f"[RoundRobin] 🔄 Bắt đầu Vòng {round_num} (quét xoay vòng tối đa {batch_size} bài/nguồn)...")

            for source_id, adapter in adapters.items():
                if not is_manual_fe:
                    await priority_coordinator.yield_if_fe_active(f"Daily Scheduler Round {round_num} - {source_id}")
                run = crawl_runs[source_id]
                urls = discovered_map.get(source_id, [])
                start_idx = index_map[source_id]
                
                if start_idx >= len(urls):
                    continue  # Source has finished all discovered URLs

                batch_urls = urls[start_idx : start_idx + batch_size]
                index_map[source_id] += len(batch_urls)
                active_in_this_round += len(batch_urls)

                logger.info(f"[RoundRobin Vòng {round_num}] [{source_id}] Xử lý batch {len(batch_urls)} bài (Vị trí {start_idx + 1}..{start_idx + len(batch_urls)} trên tổng {len(urls)} bài)...")

                for url in batch_urls:
                    if not is_manual_fe:
                        await priority_coordinator.yield_if_fe_active(f"Daily Scheduler Item - {source_id}")
                    try:
                        raw_doc = await adapter.fetch(url)
                        parsed = await adapter.parse(raw_doc)
                        item_crawled_at = utc_now()
                        parsed.published_at = publication_or_crawl_time(
                            parsed.published_at, item_crawled_at
                        )

                        # Timeframe check
                        if since and (not parsed.published_at or parsed.published_at < since):
                            run.filtered_out += 1
                            continue

                        # Deduplication check
                        fingerprint = compute_fingerprint(url, parsed.title, parsed.published_at)
                        existing = db.query(Lead).filter(or_(Lead.content_fingerprint == fingerprint, Lead.source_url == url)).first()
                        if existing:
                            run.duplicate_leads += 1
                            logger.info(f"[{source_id}] Duplicate skipped: '{parsed.title[:35]}...'")
                            continue

                        # Custom sites crawl every page; provider keyword feeds were already filtered upstream.
                        if getattr(adapter, "is_generic", False) or getattr(adapter, "is_keyword_feed", False):
                            category = "Nguồn tìm theo từ khóa" if getattr(adapter, "is_keyword_feed", False) else "Website tùy chỉnh"
                            is_rel, matched_kws, matched_cats = True, [], [category]
                        else:
                            is_rel, matched_kws, matched_cats = prefilter_keywords(
                                parsed.title, parsed.raw_content
                            )
                        if not is_rel:
                            run.filtered_out += 1
                            continue

                        # AI Extraction (round 1), then verified organization enrichment (round 2).
                        extracted = await self._extract_with_priority(parsed.title, parsed.raw_content, source=source_id, raise_on_api_error=True)
                        enrichment = await self._enrich_company(extracted)
                        combined_categories = list(set(matched_cats + extracted.need_categories))

                        # AI Lead Scoring
                        deadline_dt = parse_datetime(extracted.deadline) if extracted.deadline else None
                        score_res = await self._score_with_priority(
                            title=parsed.title,
                            need_summary=extracted.need_summary,
                            need_categories=combined_categories,
                            budget_value=extracted.budget_value,
                            location=extracted.location,
                            contact_email=extracted.contact_email,
                            contact_phone=extracted.contact_phone,
                            deadline=deadline_dt,
                            published_at=parsed.published_at,
                            relevance=extracted.relevance,
                            raw_evidence=extracted.evidence,
                        )

                        # Persist every keyword-related item successfully processed by AI.
                        lead = Lead(
                            source=source_id,
                            source_url=url,
                            title=parsed.title,
                            published_at=parsed.published_at,
                            crawled_at=item_crawled_at,
                            organization_name=extracted.organization_name,
                            organization_type=extracted.organization_type or "other",
                            need_summary=extracted.need_summary,
                            need_categories=combined_categories,
                            budget_value=extracted.budget_value,
                            budget_text=extracted.budget_text,
                            location=extracted.location,
                            contact_name=extracted.contact_name,
                            contact_email=extracted.contact_email,
                            contact_phone=extracted.contact_phone,
                            deadline=deadline_dt,
                            keywords_matched=matched_kws,
                            relevance=extracted.relevance,
                            score=score_res.total_score,
                            recommended_action=score_res.recommended_action,
                            score_reasons=score_res.reasons,
                            evidence=extracted.evidence,
                            sales_strategy=score_res.sales_strategy_suggestion,
                            raw_content_ref=raw_doc.snapshot_path,
                            content_fingerprint=fingerprint,
                            status="NEW",
                            enrichment_status=enrichment.status,
                            enrichment_message=enrichment.message,
                        )
                        db.add(lead)
                        db.flush()
                        organization = company_enrichment_service.persist(db, lead, enrichment)
                        run.new_leads += 1
                        db.commit()
                        db.refresh(lead)
                        await priority_coordinator.run_blocking(
                            google_sheets_service.upsert_lead,
                            lead,
                            worker_name="Google Sheets lead upsert",
                        )
                        if organization is not None:
                            await priority_coordinator.run_blocking(
                                google_sheets_service.upsert_organization_profile,
                                organization.id,
                                worker_name="Google Sheets organization upsert",
                            )
                        logger.info(f"[{source_id}] ✅ Đã lưu bài liên quan sau AI: '{parsed.title[:40]}...' (Score: {score_res.total_score} - {score_res.recommended_action})")

                    except AIAuthenticationError as auth_err:
                        db.rollback()
                        run.error_count += 1
                        run.status = CrawlStatusEnum.PARTIAL.value
                        run.error_message = f"AI authentication failed: {auth_err}"
                        stop_all = True
                        logger.error(
                            "[%s] AI authentication failed; stopping without saving unprocessed data: %s",
                            source_id,
                            auth_err,
                        )
                        break
                    except AIQuotaOrAPIError as quota_err:
                        db.rollback()
                        logger.warning(f"[{source_id}] ⚠️ Gemini API Quota limit: {quota_err}")
                        if timeframe == "1_month":
                            logger.warning(f"[RoundRobin] 🛑 Dừng vòng lặp crawl 1 tháng an toàn do hết hạn mức AI.")
                            run.status = CrawlStatusEnum.PARTIAL.value
                            run.error_message = f"Hết quota AI: {quota_err}"
                            stop_all = True
                            break
                        else:
                            run.error_count += 1
                            logger.warning(
                                "[%s] AI unavailable; skipped unprocessed item and will retry on a later crawl: %s",
                                source_id,
                                url,
                            )


                    except Exception as item_err:
                        db.rollback()
                        logger.warning(f"[{source_id}] Item error {url}: {item_err}")
                        run.error_count += 1
                        try:
                            db.commit()
                        except Exception:
                            db.rollback()

                if stop_all:
                    break

            if stop_all or active_in_this_round == 0:
                logger.info(f"[RoundRobin] ✅ Vòng lặp xoay vòng hoàn tất sau {round_num} rounds.")
                break

            round_num += 1

        # 3. Finalize all CrawlRun statuses
        for source_id, run in crawl_runs.items():
            if run.status == CrawlStatusEnum.RUNNING.value:
                run.status = CrawlStatusEnum.SUCCESS.value if run.error_count == 0 else CrawlStatusEnum.PARTIAL.value
            run.end_time = utc_now()
            try:
                db.commit()
            except Exception:
                db.rollback()
            source_service.record_status(
                source_id,
                run.status,
                None if run.error_count == 0 and run.status != CrawlStatusEnum.FAILED.value
                else (run.error_message or f"{run.error_count} trang lỗi"),
            )

        db.expunge_all()
        db.close()
        return list(crawl_runs.values())


crawler_service = CrawlerService()


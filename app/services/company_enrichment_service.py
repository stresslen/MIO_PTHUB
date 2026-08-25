from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import re
import uuid
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.crawlers.generic import GenericWebsiteAdapter
from app.models.organization import Organization, OrganizationContact, OrganizationEvidence
from app.pipeline.extract import AIAuthenticationError, AIQuotaOrAPIError, ai_extractor
from app.pipeline.normalize import canonicalize_url, normalize_phone_numbers, normalize_unicode, utc_now
from app.services.source_service import validate_public_url
from app.services.xah_search_service import xah_search_service

logger = logging.getLogger(__name__)

PROFILE_FIELDS = (
    "industry", "size", "locations", "employee_count", "technologies",
    "projects", "contacts", "decision_makers",
)
RELEVANT_PATH = re.compile(
    r"(?:about|gioi-thieu|company|profile|leadership|lanh-dao|team|contact|lien-he|"
    r"service|san-pham|dich-vu|project|du-an|case-stud|news|tin-tuc|career|tuyen-dung|"
    r"job|tender|dau-thau|procurement|annual|report|bao-cao|nang-luc)", re.I,
)


class CompanyEnrichmentResult(BaseModel):
    status: str
    message: str | None = None
    organization: dict[str, Any] = Field(default_factory=dict)
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    xah_used: bool = False


class CompanyEnrichmentService:
    # Verified round-two crawler. Every stored fact must carry a real URL.

    @staticmethod
    def _root_url(url: str) -> str:
        parsed = urlparse(canonicalize_url(url))
        return urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))

    @staticmethod
    def _dedupe(values: Iterable[Any]) -> list[Any]:
        output, seen = [], set()
        for value in values:
            if value in (None, "", [], {}):
                continue
            key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                output.append(value)
        return output

    @staticmethod
    def _fetch_public_page(url: str, max_chars: int = 12000) -> dict[str, str]:
        # Directly fetch an XAH result URL; redirects are validated one by one.
        current = canonicalize_url(url)
        for _ in range(4):
            valid, reason = validate_public_url(current, resolve_dns=True)
            if not valid:
                raise RuntimeError(reason or "URL không an toàn")
            response = requests.get(
                current,
                headers={
                    "User-Agent": settings.crawler_user_agent,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.2",
                    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.7",
                },
                timeout=min(settings.crawl_timeout_seconds, 30),
                allow_redirects=False,
                verify=False,
                stream=True,
            )
            if response.is_redirect or response.is_permanent_redirect:
                target = response.headers.get("Location")
                if not target:
                    raise RuntimeError("Redirect không có Location")
                current = canonicalize_url(urljoin(current, target))
                continue
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            is_pdf = "application/pdf" in content_type or urlparse(current).path.lower().endswith(".pdf")
            if content_type and not is_pdf and not any(v in content_type for v in ("html", "text/plain", "xhtml")):
                raise RuntimeError(f"Không hỗ trợ nội dung {content_type.split(';')[0]}")
            chunks, total = [], 0
            size_limit = 10_000_000 if is_pdf else 2_000_000
            for chunk in response.iter_content(16384):
                if not chunk:
                    continue
                total += len(chunk)
                if total > size_limit:
                    raise RuntimeError(f"Tài liệu vượt giới hạn {size_limit // 1_000_000} MB")
                chunks.append(chunk)
            payload = b"".join(chunks)
            if is_pdf:
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(payload))
                    text = normalize_unicode(" ".join((page.extract_text() or "") for page in reader.pages[:80]))[:max_chars]
                except Exception as exc:
                    raise RuntimeError(f"Không đọc được PDF text; PDF scan cần OCR: {exc}") from exc
                if len(text) < 40:
                    raise RuntimeError("PDF không có lớp text; cần OCR")
                return {"url": current, "title": urlparse(current).path.rsplit("/", 1)[-1] or current, "text": text}
            encoding = response.encoding or response.apparent_encoding or "utf-8"
            soup = BeautifulSoup(payload.decode(encoding, errors="replace"), "html.parser")
            for node in soup(["script", "style", "noscript", "template", "svg", "canvas", "form"]):
                node.decompose()
            title_node = soup.find("title")
            title = normalize_unicode(title_node.get_text(" ", strip=True) if title_node else current)[:500]
            content_node = soup.find("article") or soup.find("main") or soup.body or soup
            text = normalize_unicode(content_node.get_text(" ", strip=True))[:max_chars]
            if len(text) < 40:
                raise RuntimeError("Trang không có đủ nội dung HTML tĩnh")
            return {"url": current, "title": title, "text": text}
        raise RuntimeError("Quá nhiều redirect")

    @staticmethod
    def _query_prompt(name: str, tax_code: str | None, location: str | None, missing: list[str]) -> str:
        return f'''Bạn chỉ tạo truy vấn tìm kiếm, không đoán URL hay dữ liệu.
Tổ chức: {name}
Mã số thuế: {tax_code or "không có"}
Địa điểm: {location or "không có"}
Thông tin cần tìm: {", ".join(missing) if missing else "website chính thức"}
Trả duy nhất JSON: {{"queries":["2 đến 3 truy vấn tiếng Việt có tên tổ chức và loại thông tin cần tìm"]}}'''

    def _make_queries(self, name: str, tax_code: str | None, location: str | None, missing: list[str]) -> list[str]:
        data = ai_extractor._call_gemini_json(self._query_prompt(name, tax_code, location, missing))
        queries = [normalize_unicode(str(v))[:500] for v in data.get("queries") or [] if normalize_unicode(str(v))]
        if not queries:
            raise AIQuotaOrAPIError("Gemini không tạo được search query hợp lệ")
        return self._dedupe(queries)[:max(1, settings.company_xah_max_queries)]

    @staticmethod
    def _search_queries(queries: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
        results, errors, seen = [], [], set()
        for query in queries:
            try:
                payload = xah_search_service.search(query)
                for item in payload.get("results") or []:
                    url = canonicalize_url(str(item.get("url") or ""))
                    valid, _ = validate_public_url(url, resolve_dns=False)
                    if not url or not valid or url in seen:
                        continue
                    seen.add(url)
                    clean = dict(item)
                    clean.update(url=url, query=query)
                    results.append(clean)
            except Exception as exc:
                errors.append(f"{query}: {exc}")
        return results, errors

    def _load_search_urls(self, results: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
        pages, errors = [], []
        limit = settings.xah_max_results * max(1, settings.company_xah_max_queries)
        for item in results[:limit]:
            try:
                pages.append(self._fetch_public_page(item["url"]))
            except Exception as exc:
                errors.append(f"{item['url']}: {exc}")
        return pages, errors

    @staticmethod
    def _candidate_context(results: list[dict[str, Any]], pages: list[dict[str, str]]) -> str:
        page_map = {item["url"]: item for item in pages}
        blocks = []
        for index, item in enumerate(results, 1):
            page = page_map.get(item["url"], {})
            blocks.append(f'''[URL {index}]
URL: {item["url"]}
Tiêu đề: {item.get("title") or ""}
Đoạn XAH: {item.get("snippet") or ""}
Nội dung backend tải: {page.get("text", "(không tải được)")[:6000]}''')
        return "\n\n".join(blocks)

    def _discover_official_url(self, name: str, tax_code: str | None, location: str | None):
        if settings.company_enrichment_mode != "xah":
            return None, 0.0, "WEBSITE_NOT_FOUND", [], False
        if not settings.xah_api_key:
            return None, 0.0, "DISCOVERY_FAILED", ["Chưa cấu hình XAH_API_KEY"], False
        queries = self._make_queries(name, tax_code, location, ["website chính thức", "địa chỉ", "mã số thuế"])
        results, search_errors = self._search_queries(queries)
        if not results:
            return None, 0.0, "DISCOVERY_FAILED", search_errors or ["XAH không trả URL ứng viên"], True
        pages, fetch_errors = self._load_search_urls(results)
        data = ai_extractor._call_gemini_json(f'''Bạn xác minh website chính thức từ URL thật do backend cung cấp.
Tổ chức: {name}
Mã số thuế: {tax_code or "không có"}
Địa điểm: {location or "không có"}
{self._candidate_context(results, pages)}
Quy tắc: không tạo URL mới; chỉ VERIFIED khi tên pháp lý và ít nhất một tín hiệu địa chỉ, mã số thuế, email domain hoặc trang giới thiệu khớp. official_url phải cùng domain một URL trên.
Trả duy nhất JSON: {{"status":"VERIFIED|WEBSITE_AMBIGUOUS|WEBSITE_NOT_FOUND","official_url":null,"confidence":0.0,"matched_evidence":[],"message":"..."}}''')
        status = str(data.get("status") or "WEBSITE_AMBIGUOUS").upper()
        official = canonicalize_url(str(data.get("official_url") or ""))
        candidate_hosts = {(urlparse(item["url"]).hostname or "").lower().removeprefix("www.") for item in results}
        official_host = (urlparse(official).hostname or "").lower().removeprefix("www.")
        if status != "VERIFIED" or not official or official_host not in candidate_hosts:
            safe_status = status if status in {"WEBSITE_AMBIGUOUS", "WEBSITE_NOT_FOUND"} else "WEBSITE_AMBIGUOUS"
            return None, 0.0, safe_status, fetch_errors, True
        valid, reason = validate_public_url(official, resolve_dns=True)
        if not valid:
            return None, 0.0, "WEBSITE_AMBIGUOUS", [reason or "URL không an toàn"], True
        return self._root_url(official), float(data.get("confidence") or 0.0), "VERIFIED", fetch_errors, True

    async def _crawl_official_site(self, official_url: str) -> tuple[str, list[str], list[str]]:
        adapter = GenericWebsiteAdapter({
            "id": f"org-{uuid.uuid4().hex[:10]}",
            "name": urlparse(official_url).netloc,
            "seed_urls": [official_url],
            "rate_limit_delay": max(0.2, settings.default_rate_limit_delay),
            "timeout": min(settings.crawl_timeout_seconds, 30),
        })
        adapter.max_pages = max(1, min(settings.company_profile_max_pages, 100))
        adapter.max_depth = max(1, min(settings.company_profile_max_depth, 3))
        urls = await adapter.discover(max_items=adapter.max_pages)
        urls.sort(key=lambda v: (0 if RELEVANT_PATH.search(urlparse(v).path) else 1, len(v)))
        blocks, used, errors, pdf_urls = [], [], [], []
        remaining = max(10000, settings.company_profile_context_chars)
        official_host = (urlparse(official_url).hostname or "").lower().removeprefix("www.")
        for url in urls:
            if remaining <= 0:
                break
            try:
                raw_document = await adapter.fetch(url)
                soup = BeautifulSoup(raw_document.html, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    candidate = canonicalize_url(urljoin(url, str(anchor.get("href") or "")))
                    candidate_host = (urlparse(candidate).hostname or "").lower().removeprefix("www.")
                    if candidate.lower().split("?", 1)[0].endswith(".pdf") and candidate_host == official_host and candidate not in pdf_urls:
                        pdf_urls.append(candidate)
                parsed = await adapter.parse(raw_document)
                excerpt = parsed.raw_content[:min(3000, remaining)]
                if len(excerpt) < 80:
                    continue
                blocks.append(f"URL: {url}\nTiêu đề: {parsed.title}\nNội dung: {excerpt}")
                used.append(url)
                remaining -= len(excerpt)
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        for pdf_url in pdf_urls[:10]:
            if remaining <= 0:
                break
            try:
                page = await asyncio.to_thread(self._fetch_public_page, pdf_url, min(12000, remaining))
                blocks.append(f"URL: {page['url']}\nTiêu đề: {page['title']}\nNội dung PDF: {page['text']}")
                used.append(page["url"])
                remaining -= len(page["text"])
            except Exception as exc:
                errors.append(f"{pdf_url}: {exc}")
        if not blocks:
            raise RuntimeError(errors[0] if errors else "Không có trang hồ sơ đọc được")
        return "\n\n---\n\n".join(blocks), used, errors

    @staticmethod
    def _profile_prompt(name: str, org_type: str | None, tax_code: str | None, official_url: str,
                        website_context: str, supplemental_context: str = "") -> str:
        supplemental = f"\nDỮ LIỆU URL XAH ĐÃ ĐƯỢC BACKEND TẢI:\n{supplemental_context}" if supplemental_context else ""
        return f'''Bạn trích xuất Company Profile có kiểm chứng, chỉ dùng nội dung và URL trong prompt.
Tổ chức vòng 1: {name}
Loại tổ chức: {org_type or "chưa rõ"}
Mã số thuế vòng 1: {tax_code or "chưa có"}
Website đã xác minh: {official_url}
DỮ LIỆU CRAWL WEBSITE CHÍNH THỨC:
{website_context}
{supplemental}
Quy tắc tuyệt đối:
- Không tạo tên người, chức danh, email, điện thoại, doanh thu, công nghệ hay dự án.
- Không suy diễn email theo mẫu. Không có bằng chứng thì null hoặc [].
- Mỗi contact và dữ liệu quan trọng phải có source_url thật xuất hiện trong prompt và evidence_text trực tiếp.
- Chỉ xếp hạng người thực sự tìm thấy. role_group: economic_buyer, technical_buyer, process_buyer, champion hoặc other.
- Không trích xuất lịch sử tương tác nội bộ từ website.
Trả duy nhất JSON:
{{"legal_name":"tên có bằng chứng","aliases":[],"tax_code":null,"industry":null,"size":null,"locations":[],"revenue":null,"employee_count":null,"technologies":[],"projects":[{{"name":"...","summary":"...","source_url":"..."}}],"news":[{{"title":"...","published_at":null,"source_url":"..."}}],"jobs":[{{"title":"...","source_url":"..."}}],"tenders":[{{"title":"...","source_url":"..."}}],"contacts":[{{"full_name":null,"raw_title":null,"role_group":"other","email":null,"phone":null,"profile_url":null,"source_url":"...","evidence_text":"...","decision_score":null,"decision_reason":null}}],"evidence":[{{"field":"industry","value":"...","source_url":"...","evidence_text":"...","confidence":0.0}}],"missing_information":[],"search_queries":[]}}'''

    @staticmethod
    def _source_allowed(url: str, allowed_urls: set[str]) -> bool:
        # Evidence URLs must be exact URLs supplied to Gemini, not invented paths on a known domain.
        return canonicalize_url(url) in allowed_urls

    def _normalize_profile(self, data: dict[str, Any], name: str, official_url: str,
                           allowed_urls: list[str]):
        allowed = {canonicalize_url(v) for v in allowed_urls if v}
        profile = {
            "legal_name": normalize_unicode(str(data.get("legal_name") or name))[:300],
            "aliases": self._dedupe(data.get("aliases") or []), "official_url": official_url,
            "tax_code": normalize_unicode(str(data.get("tax_code") or "")) or None,
            "industry": normalize_unicode(str(data.get("industry") or "")) or None,
            "size": normalize_unicode(str(data.get("size") or "")) or None,
            "locations": self._dedupe(data.get("locations") or []), "revenue": data.get("revenue"),
            "employee_count": normalize_unicode(str(data.get("employee_count") or "")) or None,
            "technologies": self._dedupe(data.get("technologies") or []),
            "projects": self._dedupe(data.get("projects") or []),
            "news": self._dedupe(data.get("news") or []), "jobs": self._dedupe(data.get("jobs") or []),
            "tenders": self._dedupe(data.get("tenders") or []),
        }
        for field in ("projects", "news", "jobs", "tenders"):
            profile[field] = [v for v in profile[field] if isinstance(v, dict) and self._source_allowed(str(v.get("source_url") or ""), allowed)]
        contacts = []
        for item in data.get("contacts") or []:
            if not isinstance(item, dict):
                continue
            source_url = canonicalize_url(str(item.get("source_url") or ""))
            evidence_text = normalize_unicode(str(item.get("evidence_text") or ""))
            if not source_url or not evidence_text or not self._source_allowed(source_url, allowed):
                continue
            try:
                score = max(0, min(100, int(item["decision_score"]))) if item.get("decision_score") is not None else None
            except (TypeError, ValueError):
                score = None
            contacts.append({
                "full_name": normalize_unicode(str(item.get("full_name") or "")) or None,
                "raw_title": normalize_unicode(str(item.get("raw_title") or "")) or None,
                "role_group": str(item.get("role_group") or "other"),
                "email": normalize_unicode(str(item.get("email") or "")) or None,
                "phone": normalize_phone_numbers(item.get("phone")),
                "profile_url": canonicalize_url(str(item.get("profile_url") or "")) or None,
                "source_url": source_url, "evidence_text": evidence_text, "decision_score": score,
                "decision_reason": normalize_unicode(str(item.get("decision_reason") or "")) or None,
            })
        evidence = []
        for item in data.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            source_url = canonicalize_url(str(item.get("source_url") or ""))
            text = normalize_unicode(str(item.get("evidence_text") or ""))
            field = normalize_unicode(str(item.get("field") or ""))
            if not field or not source_url or not text or not self._source_allowed(source_url, allowed):
                continue
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
            except (TypeError, ValueError):
                confidence = 0.0
            evidence.append({"field": field[:100], "value": item.get("value"), "source_url": source_url,
                             "evidence_text": text, "confidence": confidence})
        missing = [normalize_unicode(str(v)) for v in data.get("missing_information") or [] if normalize_unicode(str(v))]
        derived = {"industry": profile["industry"], "size": profile["size"], "locations": profile["locations"],
                   "employee_count": profile["employee_count"], "technologies": profile["technologies"],
                   "projects": profile["projects"], "contacts": contacts,
                   "decision_makers": [v for v in contacts if v.get("decision_score") is not None]}
        for field in PROFILE_FIELDS:
            if not derived.get(field) and field not in missing:
                missing.append(field)
        return profile, contacts, evidence, self._dedupe(missing)

    async def enrich(self, organization_name: str | None, organization_type: str | None,
                     organization_website: str | None, organization_tax_code: str | None,
                     location: str | None) -> CompanyEnrichmentResult:
        if not settings.company_enrichment_enabled:
            return CompanyEnrichmentResult(status="DISABLED", message="Crawl vòng 2 đang tắt")
        name = normalize_unicode(str(organization_name or ""))
        if not name:
            return CompanyEnrichmentResult(status="ORGANIZATION_NOT_IDENTIFIED",
                message="Không đủ bằng chứng xác định tổ chức ở vòng 1", missing_information=["organization_name"])
        logger.info("[company_enrichment] Bắt đầu vòng 2 cho tổ chức: %s", name)
        official_url = canonicalize_url(str(organization_website or ""))
        confidence, discovery_status, notes, xah_used = 0.0, "VERIFIED", [], False
        if official_url:
            valid, reason = validate_public_url(official_url, resolve_dns=True)
            if valid:
                official_url, confidence = self._root_url(official_url), 1.0
            else:
                official_url, notes = "", [reason or "Website trong nguồn không an toàn"]
        if not official_url:
            try:
                official_url, confidence, discovery_status, extra, used = self._discover_official_url(name, organization_tax_code, location)
                notes.extend(extra)
                xah_used = xah_used or used
            except Exception as exc:
                return CompanyEnrichmentResult(status="DISCOVERY_FAILED", message=str(exc),
                    missing_information=["official_url"], xah_used=xah_used)
        if not official_url:
            logger.warning("[company_enrichment] Không xác minh được website cho %s: %s", name, discovery_status)
            return CompanyEnrichmentResult(status=discovery_status,
                message="; ".join(notes) or "Không xác minh được website chính thức",
                missing_information=["official_url"], xah_used=xah_used)

        logger.info("[company_enrichment] Website chính thức đã xác minh: %s (confidence=%.2f)", official_url, confidence)
        crawl_error, website_context, crawled_urls = None, "", []
        try:
            website_context, crawled_urls, crawl_notes = await self._crawl_official_site(official_url)
            logger.info("[company_enrichment] Đã đọc %s URL website chính thức", len(crawled_urls))
            notes.extend(crawl_notes[:3])
        except Exception as exc:
            crawl_error = str(exc)
            website_context = f"Website đã xác minh nhưng backend không tải được: {crawl_error}"
            crawled_urls = [official_url]
        initial_data, extraction_error = {}, None
        if not crawl_error:
            try:
                initial_data = ai_extractor._call_gemini_json(self._profile_prompt(
                    name, organization_type, organization_tax_code, official_url, website_context))
            except Exception as exc:
                extraction_error = str(exc)
        profile, contacts, evidence, missing = self._normalize_profile(initial_data, name, official_url, crawled_urls)
        if crawl_error:
            missing = list(PROFILE_FIELDS)
        all_urls, supplemental_error = list(crawled_urls), None
        if (missing or crawl_error) and settings.company_enrichment_mode == "xah":
            logger.info("[company_enrichment] Vòng 2 còn thiếu/lỗi; yêu cầu Gemini tạo query XAH: %s", ", ".join(missing))
            xah_used = True
            if not settings.xah_api_key:
                supplemental_error = "Chưa cấu hình XAH_API_KEY"
            else:
                try:
                    queries = self._make_queries(name, organization_tax_code, location, missing)
                    results, search_errors = self._search_queries(queries)
                    pages, fetch_errors = self._load_search_urls(results)
                    all_urls.extend(item["url"] for item in results)
                    all_urls.extend(item["url"] for item in pages)
                    if not results:
                        supplemental_error = "; ".join(search_errors) or "XAH không trả URL bổ sung"
                    else:
                        final_data = ai_extractor._call_gemini_json(self._profile_prompt(
                            name, organization_type, organization_tax_code, official_url, website_context,
                            self._candidate_context(results, pages)))
                        profile, contacts, evidence, missing = self._normalize_profile(final_data, name, official_url, all_urls)
                        notes.extend((search_errors + fetch_errors)[:3])
                except Exception as exc:
                    supplemental_error = str(exc)
        if not missing:
            status = "COMPLETE"
        elif crawl_error and supplemental_error:
            status = "SECOND_CRAWL_BLOCKED"
        elif extraction_error and supplemental_error:
            status = "AI_EXTRACTION_FAILED"
        else:
            status = "PROFILE_INCOMPLETE"
        messages = self._dedupe([v for v in [crawl_error, extraction_error, supplemental_error, *notes[:3]] if v])
        profile.update(organization_type=organization_type, verification_confidence=confidence)
        logger.info("[company_enrichment] Hoàn tất %s với trạng thái %s; XAH=%s", name, status, xah_used)
        return CompanyEnrichmentResult(status=status, message="; ".join(messages) or None,
            organization=profile, contacts=contacts, evidence=evidence,
            missing_information=missing, source_urls=self._dedupe(all_urls), xah_used=xah_used)

    @staticmethod
    def persist(db: Session, lead: Any, result: CompanyEnrichmentResult) -> Organization | None:
        lead.enrichment_status, lead.enrichment_message = result.status, result.message
        profile = result.organization
        if not profile or not profile.get("legal_name"):
            return None
        official_url = str(profile.get("official_url") or "")
        domain = (urlparse(official_url).hostname or "").lower().removeprefix("www.") or None
        tax_code = str(profile.get("tax_code") or "").strip() or None
        filters = []
        if domain:
            filters.append(Organization.domain == domain)
        if tax_code:
            filters.append(Organization.tax_code == tax_code)
        if not filters:
            filters.append(func.lower(Organization.legal_name) == str(profile["legal_name"]).lower())
        organization = db.query(Organization).filter(or_(*filters)).first()
        if organization is None:
            organization = Organization(legal_name=str(profile["legal_name"]))
            db.add(organization)
            db.flush()
        for field in ("legal_name", "aliases", "official_url", "tax_code", "organization_type", "industry", "size",
                      "locations", "revenue", "employee_count", "technologies", "projects", "news", "jobs", "tenders"):
            setattr(organization, field, profile.get(field))
        organization.domain = domain
        organization.profile_status = result.status
        organization.missing_information = result.missing_information
        organization.verification_confidence = float(profile.get("verification_confidence") or 0.0)
        organization.xah_used = 1 if result.xah_used else 0
        organization.source_urls = result.source_urls
        organization.error_message = result.message
        organization.verified_at = utc_now()
        db.query(OrganizationContact).filter(OrganizationContact.organization_id == organization.id).delete(synchronize_session=False)
        db.query(OrganizationEvidence).filter(OrganizationEvidence.organization_id == organization.id).delete(synchronize_session=False)
        for item in result.contacts:
            contact_key = "|".join([organization.id, str(item.get("full_name") or ""),
                                    str(item.get("raw_title") or ""), str(item.get("source_url") or "")])
            contact_id = hashlib.sha256(contact_key.encode("utf-8")).hexdigest()[:36]
            db.add(OrganizationContact(id=contact_id, organization_id=organization.id, full_name=item.get("full_name"),
                raw_title=item.get("raw_title"), role_group=item.get("role_group"), email=item.get("email"),
                phone=item.get("phone"), profile_url=item.get("profile_url"), source_url=item["source_url"],
                evidence_text=item.get("evidence_text"), decision_score=item.get("decision_score"),
                decision_reason=item.get("decision_reason"), verified_at=utc_now()))
        for item in result.evidence:
            evidence_key = "|".join([organization.id, str(item.get("field") or ""),
                                     str(item.get("source_url") or ""), str(item.get("evidence_text") or "")])
            evidence_id = hashlib.sha256(evidence_key.encode("utf-8")).hexdigest()[:36]
            db.add(OrganizationEvidence(id=evidence_id, organization_id=organization.id, field=item["field"], value=item.get("value"),
                source_url=item["source_url"], evidence_text=item["evidence_text"], crawled_at=utc_now(),
                confidence=item.get("confidence") or 0.0))
        lead.organization_id = organization.id
        return organization

    @staticmethod
    def read_profile(db: Session, organization_id: str | None) -> dict[str, Any] | None:
        if not organization_id:
            return None
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if org is None:
            return None
        contacts = db.query(OrganizationContact).filter(OrganizationContact.organization_id == org.id).order_by(OrganizationContact.decision_score.desc()).all()
        evidence = db.query(OrganizationEvidence).filter(OrganizationEvidence.organization_id == org.id).all()
        return {"id": org.id, "legal_name": org.legal_name, "aliases": org.aliases or [],
            "official_url": org.official_url, "domain": org.domain, "tax_code": org.tax_code,
            "organization_type": org.organization_type, "industry": org.industry, "size": org.size,
            "locations": org.locations or [], "revenue": org.revenue, "employee_count": org.employee_count,
            "technologies": org.technologies or [], "projects": org.projects or [], "news": org.news or [],
            "jobs": org.jobs or [], "tenders": org.tenders or [], "profile_status": org.profile_status,
            "missing_information": org.missing_information or [], "verification_confidence": org.verification_confidence or 0.0,
            "xah_used": bool(org.xah_used), "source_urls": org.source_urls or [], "error_message": org.error_message,
            "verified_at": org.verified_at, "contacts": contacts, "evidence": evidence}


company_enrichment_service = CompanyEnrichmentService()

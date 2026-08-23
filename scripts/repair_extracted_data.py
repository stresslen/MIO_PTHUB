from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.crawlers import get_adapter
from app.crawlers.base import RawDocument
from app.database import SessionLocal
from app.models.lead import Lead
from app.pipeline.extract import AIExtractor
from app.pipeline.normalize import clean_html, utc_now
from app.services.google_sheets_service import google_sheets_service

PLACEHOLDER_ORGANIZATIONS = {
    "", "đang cập nhật", "đang chờ ai bóc tách", "không rõ", "n/a", "null"
}


def _serialize(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def repair(apply_changes: bool = False) -> dict[str, Any]:
    db = SessionLocal()
    extractor = AIExtractor()
    report: dict[str, Any] = {"scanned": 0, "changed": 0, "skipped": [], "changes": [], "sheet_synced": 0}
    changed_leads: list[Lead] = []
    try:
        for lead in db.query(Lead).all():
            report["scanned"] += 1
            snapshot = Path(lead.raw_content_ref or "")
            if not snapshot.is_file():
                report["skipped"].append({"id": lead.id, "reason": "missing snapshot"})
                continue
            try:
                html = snapshot.read_text(encoding="utf-8", errors="ignore")
                raw = RawDocument(
                    url=lead.source_url,
                    source_id=lead.source,
                    html=html,
                    text=clean_html(html),
                    snapshot_path=str(snapshot),
                )
                parsed = asyncio.run(get_adapter(lead.source).parse(raw))
                updates: dict[str, tuple[Any, Any]] = {}

                if parsed.published_at and parsed.published_at != lead.published_at:
                    updates["published_at"] = (lead.published_at, parsed.published_at)
                elif not parsed.published_at and lead.published_at and lead.published_at.microsecond:
                    # Microseconds identify the old utc_now() fallback rather than source evidence.
                    updates["published_at"] = (lead.published_at, None)

                current_org = (lead.organization_name or "").strip().lower()
                has_structured_owner = parsed.raw_content.startswith("Chủ đầu tư:")
                if has_structured_owner or current_org in PLACEHOLDER_ORGANIZATIONS:
                    organization = extractor._extract_org_name(parsed.title, parsed.raw_content)
                    if organization and organization != lead.organization_name:
                        updates["organization_name"] = (lead.organization_name, organization)

                if not updates:
                    continue

                report["changed"] += 1
                report["changes"].append({
                    "id": lead.id,
                    "title": lead.title,
                    "updates": {
                        key: {"from": _serialize(old), "to": _serialize(new)}
                        for key, (old, new) in updates.items()
                    },
                })
                if apply_changes:
                    for field, (_, value) in updates.items():
                        setattr(lead, field, value)
                    lead.updated_at = utc_now()
                    changed_leads.append(lead)

            except Exception as exc:
                report["skipped"].append({"id": lead.id, "reason": str(exc)})

        if apply_changes:
            db.commit()
            if google_sheets_service.configured:
                for lead in changed_leads:
                    db.refresh(lead)
                    report["sheet_synced"] += int(google_sheets_service.upsert_lead(lead))
    finally:
        db.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair publication dates and organization names from stored snapshots")
    parser.add_argument("--apply", action="store_true", help="Persist changes; default is dry-run")
    args = parser.parse_args()
    print(json.dumps(repair(args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

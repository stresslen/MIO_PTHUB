#!/usr/bin/env python3
"""Verification script for SQLite Migration."""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import Base, SessionLocal, engine, init_db
from app.models.keyword import KeywordItem
from app.models.lead import Lead
from app.models.organization import Organization
from app.models.setting import SystemSetting
from app.models.source import CrawlerSourceItem, CrawlJob, CrawlRun, SchedulerState
from app.services.keyword_service import keyword_service
from app.services.linkedin_settings_service import linkedin_settings_service
from app.services.scoring_prompt_service import scoring_prompt_service
from app.services.setting_service import setting_service
from app.services.source_service import source_service


def main():
    print("=" * 60)
    print("VERIFYING SQLITE MIGRATION FOR MIO")
    print("=" * 60)

    # 1. Initialize DB
    print("[1] Initializing SQLite database...")
    init_db()
    db = SessionLocal()
    try:
        leads_count = db.query(Lead).count()
        print(f"    -> Existing leads in database: {leads_count}")
    finally:
        db.close()

    # 2. System Settings
    print("[2] Testing SettingService (system_settings table)...")
    setting_service.save_setting("test_key", {"status": "ok", "val": 123})
    loaded = setting_service.load_setting("test_key")
    assert loaded.get("status") == "ok" and loaded.get("val") == 123, f"Setting load failed: {loaded}"
    print("    -> SettingService save & load: PASSED")

    # 3. Keywords
    print("[3] Testing KeywordService (keywords table)...")
    kw_state = keyword_service.bootstrap()
    print(f"    -> Keyword bootstrap loaded {kw_state['total']} keywords from {kw_state['source']}")
    assert kw_state["total"] > 0, "Keywords table is empty!"
    # Add a test keyword
    add_res = keyword_service.add("Chuyển đổi số SQLite Test", use_for_discovery=False)
    print(f"    -> Added keyword: {add_res}")
    assert any(k["keyword"] == "Chuyển đổi số SQLite Test" for k in keyword_service.snapshot()["items"])
    print("    -> KeywordService SQLite persistence: PASSED")

    # 4. Sources
    print("[4] Testing SourceService (crawler_sources table)...")
    src_state = source_service.bootstrap()
    print(f"    -> Source bootstrap loaded {src_state['total']} sources from {src_state['source']}")
    assert src_state["total"] > 0, "Sources table is empty!"
    # Check get source
    topcv = source_service.get("topcv")
    assert topcv is not None, "TopCV source not found!"
    print("    -> SourceService SQLite persistence: PASSED")

    # 5. Scoring Prompt Service
    print("[5] Testing ScoringPromptService...")
    scoring_cfg = scoring_prompt_service.get_config("scoring")
    assert scoring_cfg["storage"] == "sqlite", f"Expected storage sqlite, got {scoring_cfg['storage']}"
    assert len(scoring_cfg["prompt"]) > 100, "Prompt is too short!"
    print(f"    -> Scoring prompt storage: {scoring_cfg['storage']} (PASSED)")

    # 6. LinkedIn Settings Service
    print("[6] Testing LinkedInSettingsService...")
    li_cfg = linkedin_settings_service.get_config()
    assert li_cfg["storage"] == "sqlite", f"Expected storage sqlite, got {li_cfg['storage']}"
    assert li_cfg["max_posts_per_keyword"] >= 1, "Invalid max_posts_per_keyword!"
    print(f"    -> LinkedIn settings storage: {li_cfg['storage']} (PASSED)")

    # 7. Storage API Status
    print("[7] Testing Storage API Status...")
    from app.api.storage import storage_status
    status = storage_status()
    assert status["primary"] == "sqlite", f"Expected primary sqlite, got {status['primary']}"
    assert status["sqlite"]["exists"] is True, "leads.db file doesn't exist!"
    assert status["sqlite"]["wal_mode"] is True, "WAL mode is not enabled!"
    print(f"    -> Primary storage: {status['primary']}")
    print(f"    -> Database file: {status['sqlite']['database_file']}")
    print(f"    -> Total leads: {status['sqlite']['total_leads']}")
    print(f"    -> Storage API status: PASSED")

    print("=" * 60)
    print("ALL SQLITE MIGRATION VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    main()

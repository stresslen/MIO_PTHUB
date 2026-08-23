#!/usr/bin/env python3
"""
Test Runner using Python standard library unittest.
"""

import sys
import unittest
import asyncio
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from tests.test_pipeline import (
    test_normalize_unicode_and_html,
    test_parse_vietnamese_currency,
    test_parse_datetime,
    test_extract_location,
    test_extract_contact_info,
    test_canonicalize_url,
    test_dedup_fingerprint,
)
from tests.test_scoring import (
    test_scoring_hot_lead,
    test_scoring_qualified_lead,
    test_scoring_nurture_lead,
    test_scoring_expired_penalty,
)
from tests.test_crawlers import (
    test_adapter_registry,
    test_baodauthau_parser,
    test_chinhphu_parser,
)
from tests.test_api import (
    setup_test_db,
    test_health_endpoint,
    test_get_leads_api,
    test_filter_leads_by_action,
    test_get_lead_detail_api,
    test_stats_api,
    test_sources_api,
    test_export_csv_api,
)


class PipelineTestSuite(unittest.TestCase):
    def test_pipeline_all(self):
        test_normalize_unicode_and_html()
        test_parse_vietnamese_currency()
        test_parse_datetime()
        test_extract_location()
        test_extract_contact_info()
        test_canonicalize_url()
        test_dedup_fingerprint()


class ScoringTestSuite(unittest.TestCase):
    def test_scoring_all(self):
        test_scoring_hot_lead()
        test_scoring_qualified_lead()
        test_scoring_nurture_lead()
        test_scoring_expired_penalty()


class CrawlerTestSuite(unittest.TestCase):
    def test_crawlers_all(self):
        test_adapter_registry()
        asyncio.run(test_baodauthau_parser())
        asyncio.run(test_chinhphu_parser())


class APITestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup_test_db()

    def test_apis_all(self):
        test_health_endpoint()
        test_get_leads_api()
        test_filter_leads_by_action()
        test_get_lead_detail_api()
        test_stats_api()
        test_sources_api()
        test_export_csv_api()


if __name__ == "__main__":
    unittest.main(verbosity=2)

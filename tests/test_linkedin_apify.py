import datetime

import pytest

from app.config import settings
from app.crawlers.linkedin_apify import LinkedInApifyAdapter
from app.services.keyword_service import keyword_service
from app.services.linkedin_settings_service import (
    LinkedInSettingsService,
    linkedin_settings_service,
)


def test_linkedin_actor_input_uses_1000_posts_per_keyword_and_timeframe(monkeypatch):
    adapter = LinkedInApifyAdapter()
    monkeypatch.setattr(settings, "apify_linkedin_max_posts_per_keyword", 1000)
    since = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=7)

    payload = adapter._actor_input(["chuyển đổi số", "mua sắm CNTT"], since)

    assert payload["searchQueries"] == ["chuyển đổi số", "mua sắm CNTT"]
    assert payload["maxPosts"] == 1000
    assert payload["postedLimit"] == "week"
    assert payload["contentType"] == "jobs"
    assert payload["sortBy"] == "relevance"
    assert payload["scrapeComments"] is False
    assert payload["scrapeReactions"] is False


@pytest.mark.asyncio
async def test_linkedin_dataset_goes_to_gemini_without_article_prefilter(monkeypatch):
    adapter = LinkedInApifyAdapter()
    monkeypatch.setattr(settings, "apify_api_token", "test-only-token")
    monkeypatch.setattr(
        keyword_service,
        "get_config",
        lambda: {"discovery_search": {"keywords": ["chuyển đổi số"]}},
    )
    monkeypatch.setattr(
        linkedin_settings_service,
        "get_config",
        lambda refresh=False: {"max_posts_per_keyword": 250},
    )
    monkeypatch.setattr(
        adapter,
        "_run_actor",
        lambda payload: [
            {
                "linkedinUrl": "https://www.linkedin.com/posts/example-activity-123",
                "text": "Doanh nghiệp ABC đang tuyển chuyên gia cho dự án chuyển đổi số.",
                "postedAt": "2026-08-25T08:00:00Z",
                "author": {
                    "name": "Nguyễn Văn A",
                    "headline": "CIO",
                    "companyName": "Công ty ABC",
                },
            },
            {
                "linkedinUrl": "https://evil.example/not-linkedin",
                "text": "Không được nhận",
            },
            {
                "linkedinUrl": "https://www.linkedin.com/posts/empty-activity-456",
                "text": "",
            },
        ],
    )

    urls = await adapter.discover(
        since=datetime.datetime(2026, 8, 24),
        max_items=None,
    )
    raw = await adapter.fetch(urls[0])
    parsed = await adapter.parse(raw)

    assert adapter.is_keyword_feed is True
    assert urls == ["https://www.linkedin.com/posts/example-activity-123"]
    assert parsed.author == "Nguyễn Văn A"
    assert "Công ty ABC" in parsed.raw_content
    assert parsed.extra_metadata["author_title"] == "CIO"
    assert parsed.published_at == datetime.datetime(2026, 8, 25, 8, 0)


@pytest.mark.asyncio
async def test_linkedin_requires_backend_token(monkeypatch):
    adapter = LinkedInApifyAdapter()
    monkeypatch.setattr(settings, "apify_api_token", None)

    with pytest.raises(RuntimeError, match="APIFY_API_TOKEN"):
        await adapter.discover()

class FakeSettingsSheets:
    configured = True
    last_error = None

    def __init__(self):
        self.values = {}

    def load_setting(self, key):
        return self.values.get(key)

    def save_setting(self, key, value):
        self.values[key] = dict(value)
        return True


def test_linkedin_runtime_limit_is_persisted_and_validated():
    sheets = FakeSettingsSheets()
    service = LinkedInSettingsService(sheets)

    initial = service.get_config(refresh=True)
    updated = service.update(375)
    restored = LinkedInSettingsService(sheets).get_config(refresh=True)

    assert initial["max_posts_per_keyword"] == 1000
    assert updated["max_posts_per_keyword"] == 375
    assert restored["max_posts_per_keyword"] == 375
    assert sheets.values["linkedin_apify_config"]["max_posts_per_keyword"] == 375

    with pytest.raises(ValueError, match="từ 1 đến 1000"):
        service.update(1001)

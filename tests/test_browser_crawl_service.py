from pathlib import Path
from types import SimpleNamespace

import pytest

from app.crawlers import get_adapter
from app.services.browser_crawl_service import (
    BrowserCrawlService,
    BrowserPage,
    browser_crawl_service,
)


@pytest.mark.asyncio
async def test_shared_adapter_fetch_keeps_pipeline_raw_document(monkeypatch, tmp_path):
    adapter = get_adapter("baodauthau")
    adapter.rate_limit_delay = 0

    async def rendered_fetch(url, *, timeout, source_id):
        assert timeout == adapter.timeout
        assert source_id == "baodauthau"
        return BrowserPage(
            url="https://baodauthau.vn/bai-viet-post123.html",
            html="<html><body><main>Nội dung được render bởi JavaScript</main></body></html>",
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    monkeypatch.setattr(browser_crawl_service, "fetch", rendered_fetch)
    monkeypatch.setattr(adapter, "_save_snapshot", lambda url, html: Path(tmp_path / "raw.html"))

    raw = await adapter.fetch("https://baodauthau.vn/thong-bao-moi-thau/")

    assert raw.url == "https://baodauthau.vn/bai-viet-post123.html"
    assert "Nội dung được render" in raw.text
    assert raw.status_code == 200
    assert raw.headers["Content-Type"].startswith("text/html")


@pytest.mark.asyncio
async def test_browser_service_enables_javascript_and_dynamic_dom(monkeypatch):
    captured = {}

    class FakeBrowserConfig:
        def __init__(self, **kwargs):
            captured["browser"] = kwargs

    class FakeRunConfig:
        def __init__(self, **kwargs):
            captured["run"] = kwargs

    class FakeCacheMode:
        BYPASS = "bypass"

    class FakeCrawler:
        def __init__(self, **kwargs):
            captured["crawler"] = kwargs
            self.started = False
            self.closed = False

        async def start(self):
            self.started = True

        async def arun(self, *, url, config):
            captured["url"] = url
            return SimpleNamespace(
                success=True,
                status_code=200,
                html="<html><body><div id='app'>JS result</div></body></html>",
                error_message="",
                url=url,
                redirected_url=None,
                response_headers={"content-type": "text/html"},
            )

        async def close(self):
            self.closed = True

    service = BrowserCrawlService()
    monkeypatch.setattr(
        service,
        "_types",
        lambda: (FakeCrawler, FakeBrowserConfig, FakeCacheMode, FakeRunConfig),
    )

    page = await service.fetch("https://example.com/app", timeout=20, source_id="test")

    assert page.html.endswith("</html>")
    assert captured["browser"]["java_script_enabled"] is True
    assert captured["browser"]["enable_stealth"] is True
    assert captured["run"]["wait_until"] == "domcontentloaded"
    assert captured["run"]["flatten_shadow_dom"] is True
    assert captured["run"]["process_iframes"] is True
    assert captured["run"]["max_retries"] == 0
    crawler = service._crawler
    await service.close()
    assert crawler.closed is True


@pytest.mark.asyncio
async def test_browser_service_does_not_accept_antibot_page(monkeypatch):
    class FakeCrawler:
        async def arun(self, *, url, config):
            return SimpleNamespace(
                success=True,
                status_code=200,
                html="<html><title>Just a moment...</title></html>",
                error_message="",
                url=url,
                redirected_url=None,
                response_headers={},
            )

    class FakeRunConfig:
        def __init__(self, **kwargs):
            pass

    service = BrowserCrawlService()
    service._crawler = FakeCrawler()
    monkeypatch.setattr(
        service,
        "_types",
        lambda: (object, object, SimpleNamespace(BYPASS="bypass"), FakeRunConfig),
    )

    with pytest.raises(RuntimeError, match="trang xác minh"):
        await service.fetch("https://blocked.example", timeout=5, source_id="blocked")

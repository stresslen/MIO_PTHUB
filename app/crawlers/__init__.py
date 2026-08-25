from typing import Dict, Type

from app.crawlers.base import SourceAdapter
from app.crawlers.baodauthau import BaoDauThauAdapter
from app.crawlers.muasamcong import MuaSamCongAdapter
from app.crawlers.dauthau_asia import DauThauAsiaAdapter
from app.crawlers.chinhphu import ChinhPhuAdapter, XayDungChinhSachAdapter, CongBaoAdapter
from app.crawlers.tech_news import VietnamNetAdapter, VnExpressAdapter, MostGovAdapter
from app.crawlers.hanoi_gov import HanoiGovAdapter
from app.crawlers.generic import GenericWebsiteAdapter
from app.services.source_service import source_service

CRAWLER_REGISTRY: Dict[str, Type[SourceAdapter]] = {
    "baodauthau": BaoDauThauAdapter,
    "muasamcong": MuaSamCongAdapter,
    "dauthau_asia": DauThauAsiaAdapter,
    "chinhphu": ChinhPhuAdapter,
    "xaydungchinhsach": XayDungChinhSachAdapter,
    "congbao": CongBaoAdapter,
    "most_gov": MostGovAdapter,
    "vietnamnet": VietnamNetAdapter,
    "vnexpress": VnExpressAdapter,
    "hanoi_gov": HanoiGovAdapter,
}

ADAPTER_REGISTRY = CRAWLER_REGISTRY


def get_adapter(source_id: str) -> SourceAdapter:
    """Build an adapter from the Google Sheets-backed source registry."""
    source = source_service.get(source_id)
    if source is None:
        raise ValueError(f"Unknown crawler source ID: '{source_id}'")

    if source.get("adapter_mode") == "generic":
        return GenericWebsiteAdapter(source)

    adapter_cls = CRAWLER_REGISTRY.get(str(source.get("adapter_key") or source_id))
    if adapter_cls is None:
        raise ValueError(f"Source '{source_id}' requires an adapter update")

    adapter = adapter_cls()
    adapter.source_id = source_id
    adapter.name = source["name"]
    adapter.seed_urls = list(source["seed_urls"])
    adapter.rate_limit_delay = float(source.get("rate_limit_delay") or adapter.rate_limit_delay)
    adapter.timeout = int(source.get("timeout") or adapter.timeout)
    adapter.is_generic = False
    return adapter


def get_all_adapters(scheduled_only: bool = False) -> Dict[str, SourceAdapter]:
    adapters: Dict[str, SourceAdapter] = {}
    for source in source_service.enabled_sources(scheduled_only=scheduled_only):
        try:
            adapters[source["id"]] = get_adapter(source["id"])
        except Exception:
            continue
    return adapters


__all__ = [
    "SourceAdapter",
    "GenericWebsiteAdapter",
    "CRAWLER_REGISTRY",
    "ADAPTER_REGISTRY",
    "get_adapter",
    "get_all_adapters",
]

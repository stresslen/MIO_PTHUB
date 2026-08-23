from typing import Dict, Type
from app.crawlers.base import SourceAdapter
from app.crawlers.baodauthau import BaoDauThauAdapter
from app.crawlers.muasamcong import MuaSamCongAdapter
from app.crawlers.dauthau_asia import DauThauAsiaAdapter
from app.crawlers.chinhphu import ChinhPhuAdapter, XayDungChinhSachAdapter, CongBaoAdapter
from app.crawlers.tech_news import VietnamNetAdapter, VnExpressAdapter, MostGovAdapter
from app.crawlers.hanoi_gov import HanoiGovAdapter

# Complete Registry of 10 Active Source Adapters
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
    """Instantiate and return adapter by source_id."""
    adapter_cls = CRAWLER_REGISTRY.get(source_id)
    if not adapter_cls:
        raise ValueError(f"Unknown crawler source ID: '{source_id}'. Available: {list(CRAWLER_REGISTRY.keys())}")
    return adapter_cls()


def get_all_adapters() -> Dict[str, SourceAdapter]:
    """Return dictionary of all instantiated source adapters."""
    return {source_id: cls() for source_id, cls in CRAWLER_REGISTRY.items()}


__all__ = [
    "SourceAdapter",
    "BaoDauThauAdapter",
    "MuaSamCongAdapter",
    "DauThauAsiaAdapter",
    "ChinhPhuAdapter",
    "XayDungChinhSachAdapter",
    "CongBaoAdapter",
    "MostGovAdapter",
    "VietnamNetAdapter",
    "VnExpressAdapter",
    "HanoiGovAdapter",
    "CRAWLER_REGISTRY",
    "ADAPTER_REGISTRY",
    "get_adapter",
    "get_all_adapters",
]

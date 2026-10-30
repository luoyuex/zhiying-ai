"""热门股票解析与「腾讯→东财→过期缓存」降级测试（不访问外网）。"""

import json
import time

import pytest

from app.providers.base import ProviderUnavailable
from app.providers.hot_stocks import EastmoneyHotStocksProvider, TencentHotStocksProvider
from app.schemas.stock import HotStockItem
from app.services.hot_stock_service import HOT_CACHE_KEY, load_hot_stocks


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


def test_tencent_parse_maps_rows():
    item = TencentHotStocksProvider.parse_row(
        {
            "code": "sz300502",
            "name": "新易盛",
            "stock_type": "GP-A-CYB",
            "zxj": "196.00",
            "zdf": "-14.19",
        }
    )
    assert item is not None
    assert item.code == "300502"
    assert item.name == "新易盛"
    assert item.price == 196.0
    assert item.change_pct == -14.19


@pytest.mark.parametrize(
    "row",
    [
        {"code": "sz300502", "name": "ST新易盛", "stock_type": "GP-A-CYB", "zxj": "1", "zdf": "0"},
        {"code": "sz300502", "name": "某某退", "stock_type": "GP-A-CYB", "zxj": "1", "zdf": "0"},
        {"code": "sz159915", "name": "创业板ETF", "stock_type": "ETF", "zxj": "1", "zdf": "0"},
        {"code": "bj430047", "name": "诺思兰德", "stock_type": "GP-A-BJ", "zxj": "1", "zdf": "0"},
        {"code": "", "name": "空代码", "stock_type": "GP-A", "zxj": "1", "zdf": "0"},
    ],
)
def test_tencent_parse_skips_non_a_share(row):
    assert TencentHotStocksProvider.parse_row(row) is None


def test_eastmoney_parse_maps_rows():
    item = EastmoneyHotStocksProvider.parse_row(
        {"f12": "600519", "f14": "贵州茅台", "f2": 1392.05, "f3": 2.81}
    )
    assert item is not None
    assert item.code == "600519"
    assert item.change_pct == 2.81


async def test_hot_stocks_falls_back_to_eastmoney(monkeypatch: pytest.MonkeyPatch):
    async def tencent_fail(self, limit=8):
        raise ProviderUnavailable("tencent down")

    async def eastmoney_ok(self, limit=8):
        return [
            HotStockItem(code="600519", name="贵州茅台", price=1392.05, change_pct=2.81),
        ]

    monkeypatch.setattr(TencentHotStocksProvider, "fetch", tencent_fail)
    monkeypatch.setattr(EastmoneyHotStocksProvider, "fetch", eastmoney_ok)

    redis = FakeRedis()
    items = await load_hot_stocks(redis, limit=4)

    assert [item.code for item in items] == ["600519"]
    assert HOT_CACHE_KEY in redis.store


async def test_hot_stocks_uses_stale_cache_when_all_sources_fail(
    monkeypatch: pytest.MonkeyPatch,
):
    async def always_fail(self, limit=8):
        raise ProviderUnavailable("down")

    monkeypatch.setattr(TencentHotStocksProvider, "fetch", always_fail)
    monkeypatch.setattr(EastmoneyHotStocksProvider, "fetch", always_fail)

    redis = FakeRedis()
    redis.store[HOT_CACHE_KEY] = json.dumps(
        {
            "items": [{"code": "600519", "name": "贵州茅台", "price": 1.0, "change_pct": 0.1}],
            # 早于新鲜窗口，仍应作为兜底返回
            "fetched_at": time.time() - 3600,
        },
        ensure_ascii=False,
    )

    items = await load_hot_stocks(redis, limit=4)

    assert [item.name for item in items] == ["贵州茅台"]

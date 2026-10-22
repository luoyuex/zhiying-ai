"""资金流解析与东财→新浪降级测试（不访问外网）。"""

import pytest

from app.providers.base import ProviderUnavailable, now_shanghai
from app.providers.fundflow import (
    EastmoneyFundFlowProvider,
    SinaFundFlowProvider,
    get_fund_flow,
)
from app.providers.symbols import parse_symbol
from app.schemas.company import FundFlowData, FundFlowDay


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


def test_sina_parse_maps_and_sorts():
    rows = [
        {
            "opendate": "2026-10-22",
            "trade": "1318.49",
            "changeratio": "0.00671915",
            "netamount": "531431526.52",
            "ratioamount": "0.0953032",
            "r0_net": "500981378.23",
        },
        {
            "opendate": "2026-10-21",
            "trade": "1309.69",
            "changeratio": "-0.01",
            "netamount": "-120000000",
            "ratioamount": "-0.02",
            "r0_net": "-80000000",
        },
    ]

    days = SinaFundFlowProvider.parse(rows)

    assert [day.date for day in days] == ["2026-10-21", "2026-10-22"]
    latest = days[-1]
    assert latest.main_net == 531431526.52
    assert latest.super_large_net == 500981378.23
    assert round(latest.main_pct or 0, 4) == 9.5303
    assert round(latest.change_pct or 0, 4) == 0.6719
    assert latest.large_net is None


async def test_fund_flow_falls_back_to_sina(monkeypatch: pytest.MonkeyPatch):
    async def eastmoney_fail(self, symbol):
        raise ProviderUnavailable("Server disconnected")

    async def sina_ok(self, symbol):
        return FundFlowData(
            symbol=symbol.code,
            days=[
                FundFlowDay(
                    date="2026-10-22",
                    main_net=1.2e8,
                    main_pct=5.0,
                    close=10.5,
                    change_pct=1.2,
                )
            ],
            source="sina_fundflow",
            fetched_at=now_shanghai(),
        )

    monkeypatch.setattr(EastmoneyFundFlowProvider, "fetch", eastmoney_fail)
    monkeypatch.setattr(SinaFundFlowProvider, "fetch", sina_ok)

    redis = FakeRedis()
    data = await get_fund_flow(redis, "600519")

    assert data is not None
    assert data.source == "sina_fundflow"
    assert data.days[0].main_net == 1.2e8
    assert "mkt:fundflow:600519" in redis.store


async def test_fund_flow_all_sources_fail(monkeypatch: pytest.MonkeyPatch):
    async def fail(self, symbol):
        raise ProviderUnavailable("超时")

    monkeypatch.setattr(EastmoneyFundFlowProvider, "fetch", fail)
    monkeypatch.setattr(SinaFundFlowProvider, "fetch", fail)

    data = await get_fund_flow(FakeRedis(), "600519")

    assert data is None


def test_sina_provider_uses_prefixed_symbol():
    symbol = parse_symbol("600519")

    assert symbol.prefixed == "sh600519"

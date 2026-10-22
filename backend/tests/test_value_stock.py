"""低估值策略：估值/股息/负债过滤与 AI 选股。"""

import uuid

from app.providers.base import now_shanghai
from app.providers.models import Quote
from app.schemas.screener import (
    PerformanceRow,
    ValueStockAnalysisRequest,
    ValueStockItem,
)
from app.services import value_stock_service
from app.services.value_stock_service import ValueStockCandidateSet


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str | int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def incr(self, key: str) -> int:
        value = int(self.store.get(key, 0)) + 1
        self.store[key] = value
        return value

    async def expire(self, key: str, seconds: int) -> None:
        return None


class FakePerformance:
    async def fetch_latest_by_codes(self, codes: list[str]):
        return {
            code: PerformanceRow(
                symbol=code,
                name="测试",
                report_date="2026-06-30",
                profit_growth=12.0,
                revenue_growth=8.0,
                industry="测试行业",
            )
            for code in codes
        }


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    async def generate_text(self, *_args, **_kwargs):
        self.calls += 1
        return f"分析报告 {self.calls}"

    async def generate_json(self, *_args, **_kwargs):
        return self.payload


def make_quote(symbol: str, price: float, amount: float) -> Quote:
    return Quote(
        symbol=symbol,
        name="测试",
        price=price,
        change_pct=1.0,
        amount=amount,
        source="test",
        fetched_at=now_shanghai(),
    )


SNAPSHOT = [
    {
        "SECURITY_CODE": "600519",
        "SECURITY_NAME_ABBR": "测试A",
        "BOARD_NAME": "白酒",
        "CLOSE_PRICE": 10.0,
        "CHANGE_RATE": 1.0,
        "PE_TTM": 15.0,
        "PB_MRQ": 1.2,
        "TOTAL_MARKET_CAP": 6e9,
        "NOTLIMITED_MARKETCAP_A": 5e9,
    },
    {
        "SECURITY_CODE": "000001",
        "SECURITY_NAME_ABBR": "测试B",
        "BOARD_NAME": "银行",
        "CLOSE_PRICE": 5.0,
        "CHANGE_RATE": 1.0,
        "PE_TTM": 10.0,
        "PB_MRQ": 1.0,
        "TOTAL_MARKET_CAP": 4e9,
        "NOTLIMITED_MARKETCAP_A": 3e9,
    },
    {
        "SECURITY_CODE": "300001",
        "SECURITY_NAME_ABBR": "创业板测试",
        "BOARD_NAME": "测试",
        "CLOSE_PRICE": 5.0,
        "PE_TTM": 10.0,
        "PB_MRQ": 1.0,
        "NOTLIMITED_MARKETCAP_A": 1e9,
    },
    {
        "SECURITY_CODE": "600002",
        "SECURITY_NAME_ABBR": "*ST测试",
        "BOARD_NAME": "测试",
        "CLOSE_PRICE": 5.0,
        "PE_TTM": 10.0,
        "PB_MRQ": 1.0,
        "NOTLIMITED_MARKETCAP_A": 1e9,
    },
]


async def test_collect_value_candidates(monkeypatch):
    async def fake_snapshot(*_args, **_kwargs):
        return SNAPSHOT

    async def fake_debt(_codes, **_kwargs):
        return {"600519": 20.0, "000001": 90.0}

    async def fake_dividend(_codes, _prices, **_kwargs):
        return {"600519": 3.5, "000001": 5.0}

    async def fake_quotes(_symbols):
        return {"600519": make_quote("600519", 10.0, 50_000_000)}

    monkeypatch.setattr(value_stock_service, "fetch_valuation_snapshot", fake_snapshot)
    monkeypatch.setattr(value_stock_service, "fetch_debt_ratios", fake_debt)
    monkeypatch.setattr(value_stock_service, "fetch_dividend_yields", fake_dividend)
    monkeypatch.setattr(value_stock_service, "fetch_quotes", fake_quotes)

    candidates = await value_stock_service.collect_value_candidates(
        ValueStockAnalysisRequest(final_n=3),
        performance_provider=FakePerformance(),
    )

    assert candidates.scanned_count == 4
    assert candidates.candidate_count == 1
    assert [item.symbol for item in candidates.items] == ["600519"]
    assert candidates.items[0].debt_ratio == 20.0
    assert candidates.items[0].dividend_yield == 3.5
    assert candidates.items[0].industry == "测试行业"


async def test_analyze_value_stock(monkeypatch):
    item = ValueStockItem(
        symbol="600519",
        name="测试A",
        industry="白酒",
        price=10.0,
        change_pct=1.0,
        amount=50_000_000,
        pe=15.0,
        pb=1.2,
        dividend_yield=3.5,
        debt_ratio=20.0,
        float_market_cap=5e9,
        total_market_cap=6e9,
        profit_growth=12.0,
        revenue_growth=8.0,
        report_date="2026-06-30",
    )
    candidates = ValueStockCandidateSet(
        items=[item],
        quotes={},
        performance={},
        report_date="2026-06-30",
        scanned_count=4,
        candidate_count=1,
    )

    async def fake_collect(*_args, **_kwargs):
        return candidates

    monkeypatch.setattr(value_stock_service, "collect_value_candidates", fake_collect)
    llm = FakeLLM(
        {
            "recommendations": [
                {
                    "rank": 1,
                    "symbol": "600519",
                    "name": "错误名称",
                    "reasons": ["低估值且基本面稳健"],
                }
            ]
        }
    )
    phases: list[str] = []

    async def on_phase(phase: str) -> None:
        phases.append(phase)

    response = await value_stock_service.analyze_value_stock(
        FakeRedis(),
        uuid.uuid4(),
        5,
        ValueStockAnalysisRequest(final_n=3),
        llm_client=llm,
        on_phase=on_phase,
    )

    assert response.strategy == "value_stock"
    assert response.recommendations[0].symbol == "600519"
    assert response.recommendations[0].name == "测试A"
    assert phases == [
        "读取估值、股息与负债数据",
        "三位分析师整体分析中",
        "资深研究员精选中",
    ]

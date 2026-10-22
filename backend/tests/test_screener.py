"""主力选股：排行解析、过滤规则与接口。"""

import uuid
from datetime import datetime

from httpx import ASGITransport, AsyncClient

from app.core.deps import get_current_user
from app.db.models.user import User
from app.main import app
from app.providers.base import ProviderUnavailable, now_shanghai
from app.providers.fund_flow_rank import SinaFundFlowRankProvider
from app.providers.models import Quote
from app.providers.performance import EastmoneyPerformanceProvider
from app.schemas.screener import (
    LowPriceBullRequest,
    LowPriceBullResponse,
    MainForceScreenRequest,
    MainForceScreenResponse,
    PerformanceRow,
    SmallCapRequest,
    SmallCapResponse,
)
from app.services import screener_service


class FakeRedis:
    async def get(self, _key: str):
        return None

    async def set(self, _key: str, _value: str, ex: int | None = None) -> None:
        return None


ROWS = [
    {
        "symbol": "sh511360",
        "name": "短融ETF海富通",
        "trade": "114.0770",
        "changeratio": "0.00007",
        "r0_net": "5829699867.3",
        "r0_ratio": "0.0852256",
        "amount": "68403143939.0",
    },
    {
        "symbol": "sh603236",
        "name": "移远通信",
        "trade": "50.00",
        "changeratio": "0.03",
        "r0_net": "1320237099.64",
        "r0_ratio": "0.085",
        "amount": "1000000000",
    },
    {
        "symbol": "sz300394",
        "name": "天孚通信",
        "trade": "100.00",
        "changeratio": "0.05",
        "r0_net": "1098295551.69",
        "r0_ratio": "0.07",
        "amount": "800000000",
    },
    {
        "symbol": "sh688111",
        "name": "金山办公",
        "trade": "300.00",
        "changeratio": "0.02",
        "r0_net": "500000000",
        "r0_ratio": "0.05",
        "amount": "600000000",
    },
    {
        "symbol": "sh600000",
        "name": "ST浦发",
        "trade": "10.00",
        "changeratio": "0.01",
        "r0_net": "400000000",
        "r0_ratio": "0.04",
        "amount": "500000000",
    },
    {
        "symbol": "sz000001",
        "name": "平安银行",
        "trade": "12.00",
        "changeratio": "0.05",
        "r0_net": "300000000",
        "r0_ratio": "0.03",
        "amount": "400000000",
    },
]


def parse_rows():
    return [
        item
        for row in ROWS
        if (item := SinaFundFlowRankProvider.parse_row(row)) is not None
    ]


def test_parse_row_filters_non_stocks():
    items = parse_rows()

    assert [item.symbol for item in items] == [
        "603236",
        "300394",
        "688111",
        "600000",
        "000001",
    ]
    assert items[0].change_pct == 3.0
    assert items[0].main_net_pct == 8.5


def test_filter_main_force_rules():
    request = MainForceScreenRequest(top_n=10, max_change_pct=7.0)
    filtered = screener_service.filter_main_force(parse_rows(), request)

    assert [item.symbol for item in filtered] == ["603236", "000001"]


async def test_screen_main_force(monkeypatch):
    async def fake_fetch(self, limit: int = 300):
        return parse_rows()

    monkeypatch.setattr(SinaFundFlowRankProvider, "fetch", fake_fetch)

    response = await screener_service.screen_main_force(
        FakeRedis(),
        MainForceScreenRequest(top_n=5, max_change_pct=7.0),
    )

    assert response.strategy == "main_force"
    assert response.scanned_count == 5
    assert response.candidate_count == 2
    assert [item.symbol for item in response.items] == ["603236", "000001"]
    assert response.filters["exclude_gem"] is True


async def test_strategies_api():
    user = User(id=uuid.uuid4(), email="screener@example.com", nickname="Screener")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/screener/strategies")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body[0]["id"] == "main_force"
            assert body[0]["status"] == "available"
    finally:
        app.dependency_overrides.clear()


async def test_main_force_api(monkeypatch):
    user = User(id=uuid.uuid4(), email="screener2@example.com", nickname="Screener")

    async def fake_screen(_redis, _request):
        return MainForceScreenResponse(
            items=[],
            scanned_count=0,
            candidate_count=0,
            fetched_at=datetime.now(),
            filters={},
        )

    monkeypatch.setattr("app.api.v1.screener.screen_main_force", fake_screen)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/screener/main-force", json={"top_n": 5})
            assert response.status_code == 200, response.text
            assert response.json()["strategy"] == "main_force"
    finally:
        app.dependency_overrides.clear()


async def test_main_force_api_maps_market_error(monkeypatch):
    user = User(id=uuid.uuid4(), email="screener3@example.com", nickname="Screener")

    async def broken(_redis, _request):
        raise ProviderUnavailable("mock unavailable")

    monkeypatch.setattr("app.api.v1.screener.screen_main_force", broken)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/screener/main-force", json={"top_n": 5})
            assert response.status_code == 503
            assert response.json()["code"] == "MARKET_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


def test_performance_parse_rows():
    payload = {
        "result": {
            "data": [
                {
                    "SECURITY_CODE": "600798",
                    "SECURITY_NAME_ABBR": "宁波海运",
                    "REPORTDATE": "2026-09-30 00:00:00",
                    "SJLTZ": 135.4,
                    "YSTZ": 56.2,
                },
                {
                    "SECURITY_CODE": "511360",
                    "SECURITY_NAME_ABBR": "短融ETF",
                    "REPORTDATE": "2026-09-30 00:00:00",
                    "SJLTZ": 10,
                    "YSTZ": 5,
                },
            ]
        }
    }

    rows = EastmoneyPerformanceProvider.parse_rows(payload)

    assert len(rows) == 1
    assert rows[0].symbol == "600798"
    assert rows[0].profit_growth == 135.4
    assert rows[0].report_date == "2026-09-30"


class FakePerformanceProvider:
    async def fetch(self, _min_growth: float, _min_revenue: float = 0.0):
        return "2026-09-30", [
            PerformanceRow(
                symbol="600798",
                name="宁波海运",
                report_date="2026-09-30",
                profit_growth=135.4,
                revenue_growth=56.2,
            ),
            PerformanceRow(
                symbol="002148",
                name="北纬科技",
                report_date="2026-09-30",
                profit_growth=2246.4,
                revenue_growth=0.7,
            ),
            PerformanceRow(
                symbol="301118",
                name="恒光股份",
                report_date="2026-09-30",
                profit_growth=4845.1,
            ),
            PerformanceRow(
                symbol="688779",
                name="五矿新能",
                report_date="2026-09-30",
                profit_growth=2396.7,
            ),
            PerformanceRow(
                symbol="600001",
                name="ST测试",
                report_date="2026-09-30",
                profit_growth=300.0,
            ),
            PerformanceRow(
                symbol="830799",
                name="北交所测试",
                report_date="2026-09-30",
                profit_growth=200.0,
            ),
        ]


def make_quote(
    symbol: str,
    price: float,
    amount: float,
    market_cap: float | None = None,
) -> Quote:
    return Quote(
        symbol=symbol,
        name=f"测试{symbol}",
        price=price,
        change_pct=1.0,
        amount=amount,
        total_market_cap=market_cap,
        source="test",
        fetched_at=now_shanghai(),
    )


async def test_low_price_bull_screen(monkeypatch):
    async def fake_fetch_quotes(_symbols):
        return {
            "600798": make_quote("600798", 3.29, 52_436_307),
            "002148": make_quote("002148", 6.27, 59_388_524),
        }

    monkeypatch.setattr(screener_service, "fetch_quotes", fake_fetch_quotes)

    response = await screener_service.screen_low_price_bull(
        LowPriceBullRequest(top_n=5, max_price=10, min_profit_growth=100),
        provider=FakePerformanceProvider(),
    )

    assert response.scanned_count == 6
    assert response.candidate_count == 2
    assert [item.symbol for item in response.items] == ["600798", "002148"]
    assert response.items[0].price == 3.29
    assert response.items[0].profit_growth == 135.4
    assert response.filters["report_date"] == "2026-09-30"


async def test_low_price_bull_api(monkeypatch):
    user = User(id=uuid.uuid4(), email="lowbull@example.com", nickname="LowBull")

    async def fake_screen(_request):
        return LowPriceBullResponse(
            items=[],
            scanned_count=0,
            candidate_count=0,
            fetched_at=datetime.now(),
            filters={},
        )

    monkeypatch.setattr("app.api.v1.screener.screen_low_price_bull", fake_screen)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/screener/low-price-bull", json={"top_n": 5}
            )
            assert response.status_code == 200, response.text
            assert response.json()["strategy"] == "low_price_bull"
    finally:
        app.dependency_overrides.clear()


async def test_low_price_bull_api_maps_market_error(monkeypatch):
    user = User(id=uuid.uuid4(), email="lowbull2@example.com", nickname="LowBull")

    async def broken(_request):
        raise ProviderUnavailable("mock unavailable")

    monkeypatch.setattr("app.api.v1.screener.screen_low_price_bull", broken)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/screener/low-price-bull", json={"top_n": 5}
            )
            assert response.status_code == 503
            assert response.json()["code"] == "MARKET_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


class FakeSmallCapProvider:
    async def fetch(self, _min_profit: float, _min_revenue: float = 0.0):
        return "2026-09-30", [
            PerformanceRow(
                symbol="600798",
                name="宁波海运",
                report_date="2026-09-30",
                profit_growth=135.4,
                revenue_growth=56.2,
            ),
            PerformanceRow(
                symbol="002083",
                name="孚日股份",
                report_date="2026-09-30",
                profit_growth=135.1,
                revenue_growth=23.8,
            ),
            PerformanceRow(
                symbol="002353",
                name="杰瑞股份",
                report_date="2026-09-30",
                profit_growth=500.0,
                revenue_growth=20.0,
            ),
            PerformanceRow(
                symbol="301118",
                name="恒光股份",
                report_date="2026-09-30",
                profit_growth=4845.1,
                revenue_growth=30.0,
            ),
            PerformanceRow(
                symbol="688779",
                name="五矿新能",
                report_date="2026-09-30",
                profit_growth=2396.7,
                revenue_growth=40.0,
            ),
            PerformanceRow(
                symbol="600001",
                name="ST测试",
                report_date="2026-09-30",
                profit_growth=300.0,
                revenue_growth=50.0,
            ),
            PerformanceRow(
                symbol="830799",
                name="北交所测试",
                report_date="2026-09-30",
                profit_growth=200.0,
                revenue_growth=20.0,
            ),
        ]


async def test_small_cap_screen(monkeypatch):
    async def fake_fetch_quotes(_symbols):
        return {
            "600798": make_quote("600798", 3.29, 52_436_307, 40e8),
            "002083": make_quote("002083", 9.28, 45_240_099, 60e8),
            "002353": make_quote("002353", 91.0, 66_488_017, 30e8),
        }

    monkeypatch.setattr(screener_service, "fetch_quotes", fake_fetch_quotes)

    response = await screener_service.screen_small_cap(
        SmallCapRequest(
            top_n=5,
            max_market_cap=50,
            min_profit_growth=100,
            min_revenue_growth=10,
        ),
        provider=FakeSmallCapProvider(),
    )

    assert response.scanned_count == 7
    assert response.candidate_count == 2
    assert [item.symbol for item in response.items] == ["002353", "600798"]
    assert response.items[0].total_market_cap == 30e8
    assert response.items[0].profit_growth == 500.0
    assert response.filters["report_date"] == "2026-09-30"


async def test_small_cap_api(monkeypatch):
    user = User(id=uuid.uuid4(), email="smallcap@example.com", nickname="SmallCap")

    async def fake_screen(_request):
        return SmallCapResponse(
            items=[],
            scanned_count=0,
            candidate_count=0,
            fetched_at=datetime.now(),
            filters={},
        )

    monkeypatch.setattr("app.api.v1.screener.screen_small_cap", fake_screen)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/screener/small-cap", json={"top_n": 5})
            assert response.status_code == 200, response.text
            assert response.json()["strategy"] == "small_cap"
    finally:
        app.dependency_overrides.clear()

"""行情接口装配测试：鉴权、参数校验、错误码映射。"""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import stocks
from app.core.deps import get_current_user
from app.main import app
from app.providers.base import DataNotFound, MarketUnavailable, now_shanghai
from app.providers.models import Adjust, KlineBar, KlinePeriod, KlineSeries, Quote
from app.providers.symbols import InvalidSymbolError


class FakeMarketService:
    async def get_quote(self, code: str) -> Quote:
        if code == "bad":
            raise InvalidSymbolError("股票代码必须是 6 位数字：bad")
        if code == "000000":
            raise DataNotFound("no data")
        if code == "999999":
            raise MarketUnavailable("quote", [])
        return Quote(
            symbol=code,
            name="测试股份",
            price=10.0,
            source="fake",
            fetched_at=datetime.now().astimezone(),
        )

    async def get_kline(
        self,
        code: str,
        *,
        period: KlinePeriod,
        adjust: Adjust,
        limit: int,
    ) -> KlineSeries:
        now = datetime.now().astimezone()
        return KlineSeries(
            symbol=code,
            period=period,
            adjust=adjust,
            bars=[
                KlineBar(
                    time=now,
                    open=10.0,
                    high=10.5,
                    low=9.8,
                    close=10.2,
                    volume=1000,
                )
            ][:limit],
            source="fake",
            fetched_at=now,
        )


class FakeAnalysisService(FakeMarketService):
    async def get_quote(self, code: str) -> Quote:
        now = now_shanghai()
        return Quote(
            symbol=code,
            name="测试股份",
            price=10.89,
            pre_close=10.88,
            source="fake",
            fetched_at=now,
        )

    async def get_kline(
        self,
        code: str,
        *,
        period: KlinePeriod,
        adjust: Adjust,
        limit: int,
    ) -> KlineSeries:
        now = now_shanghai()
        bars = []
        for index in range(90):
            close = 10 + index * 0.01
            bars.append(
                KlineBar(
                    time=now - timedelta(days=90 - index),
                    open=close - 0.01,
                    high=close + 0.03,
                    low=close - 0.03,
                    close=close,
                    volume=1_000_000 + index * 2_000,
                )
            )
        return KlineSeries(
            symbol=code,
            period=period,
            adjust=adjust,
            bars=bars[-limit:],
            source="fake",
            fetched_at=now,
        )


@pytest.fixture
async def client():
    service = FakeMarketService()
    app.dependency_overrides[get_current_user] = lambda: object()
    app.dependency_overrides[stocks.get_market_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_quote_endpoint(client: AsyncClient):
    response = await client.get("/api/v1/stocks/600519/quote")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "600519"
    assert body["price"] == 10.0
    assert body["source"] == "fake"


async def test_kline_endpoint(client: AsyncClient):
    response = await client.get(
        "/api/v1/stocks/600519/kline",
        params={"period": "day", "adjust": "qfq", "limit": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["period"] == "day"
    assert body["adjust"] == "qfq"
    assert len(body["bars"]) == 1


async def test_invalid_symbol_maps_422(client: AsyncClient):
    response = await client.get("/api/v1/stocks/bad/quote")

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_SYMBOL"


async def test_not_found_maps_404(client: AsyncClient):
    response = await client.get("/api/v1/stocks/000000/quote")

    assert response.status_code == 404
    assert response.json()["code"] == "STOCK_NOT_FOUND"


async def test_unavailable_maps_503(client: AsyncClient):
    response = await client.get("/api/v1/stocks/999999/quote")

    assert response.status_code == 503
    assert response.json()["code"] == "MARKET_UNAVAILABLE"


async def test_requires_login():
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get("/api/v1/stocks/600519/quote")

    assert response.status_code == 401


async def test_analysis_endpoint(client: AsyncClient):
    app.dependency_overrides[stocks.get_market_service] = lambda: FakeAnalysisService()

    response = await client.get("/api/v1/stocks/600519/analysis")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["symbol"] == "600519"
    assert body["score"] >= 60
    assert body["rating"] in {"偏强", "强势"}
    assert body["levels"]["computed_by"] == "code"
    assert body["levels"]["stop_loss"] < body["levels"]["entry"] < body["price"]
    assert body["price"] < body["levels"]["take_profit"]
    assert body["signals"]
    assert "技术评分" in body["summary"]

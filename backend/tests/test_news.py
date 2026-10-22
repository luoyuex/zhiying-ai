"""公告/新闻 Provider、聚合缓存与接口测试（不访问外网）。"""

import json
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import stocks
from app.core.deps import get_current_user
from app.main import app
from app.providers.base import ProviderUnavailable, now_shanghai
from app.providers.models import Quote
from app.providers.news import (
    EastmoneyAnnouncementProvider,
    EastmoneyNewsSearchProvider,
)
from app.schemas.company import FundFlowData, FundFlowDay
from app.schemas.news import CompanyNewsData, NewsItem
from app.schemas.search import WebSearchResult, WebSource
from app.services.company_news_service import get_company_news


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


def make_item(kind: str, index: int = 1) -> NewsItem:
    return NewsItem(
        id=f"{kind}-{index}",
        kind=kind,
        title=f"测试{kind}{index}",
        summary="摘要",
        url=f"https://example.com/{kind}/{index}",
        source="测试源",
        published_at="2026-10-21 10:00:00",
    )


def test_parse_announcements():
    payload = {
        "data": {
            "list": [
                {
                    "art_code": "AN001",
                    "codes": [{"stock_code": "600519", "short_name": "贵州茅台"}],
                    "columns": [{"column_code": "001", "column_name": "其他"}],
                    "notice_date": "2026-08-15 00:00:00",
                    "title": "贵州茅台:关于召开业绩说明会的公告",
                },
                {
                    "art_code": "AN001",
                    "notice_date": "2026-08-15 00:00:00",
                    "title": "重复公告",
                },
            ]
        }
    }

    items = EastmoneyAnnouncementProvider.parse(payload, "600519")

    assert len(items) == 1
    item = items[0]
    assert item.kind == "announcement"
    assert item.url == "https://data.eastmoney.com/notices/detail/600519/AN001.html"
    assert item.summary == "其他"
    assert item.published_at == "2026-08-15 00:00:00"


def test_parse_news_jsonp_cleans_tags():
    payload = {
        "result": {
            "cmsArticleWebOld": [
                {
                    "code": "N001",
                    "title": "<em>贵州茅台</em>发布公告",
                    "content": "公司 <em>贵州茅台</em> 半年度 &amp; 业绩",
                    "mediaName": "测试媒体",
                    "url": "https://example.com/news/1",
                    "date": "2026-10-21 06:09:42",
                },
                {
                    "code": "N001",
                    "title": "重复",
                    "url": "https://example.com/news/1",
                    "date": "2026-10-21",
                },
            ]
        }
    }
    text = f"cb({json.dumps(payload, ensure_ascii=False)})"

    items = EastmoneyNewsSearchProvider.parse(text)

    assert len(items) == 1
    item = items[0]
    assert item.kind == "article"
    assert item.title == "贵州茅台发布公告"
    assert item.summary == "公司 贵州茅台 半年度 & 业绩"
    assert item.source == "测试媒体"


async def test_company_news_cache(monkeypatch: pytest.MonkeyPatch):
    calls = {"ann": 0, "news": 0}

    async def fake_ann(self, symbol: str, limit: int = 20):
        calls["ann"] += 1
        return [make_item("announcement")]

    async def fake_news(self, symbol: str, name: str = "", limit: int = 20):
        calls["news"] += 1
        return [make_item("article")]

    monkeypatch.setattr(EastmoneyAnnouncementProvider, "fetch", fake_ann)
    monkeypatch.setattr(EastmoneyNewsSearchProvider, "fetch", fake_news)
    redis = FakeRedis()

    first = await get_company_news(redis, "600519", name="贵州茅台")
    second = await get_company_news(redis, "600519", name="贵州茅台")

    assert calls == {"ann": 1, "news": 1}
    assert first.symbol == "600519"
    assert second.announcements[0].id == "announcement-1"
    assert "mkt:news:600519" in redis.store


async def test_single_source_failure_is_partial(monkeypatch: pytest.MonkeyPatch):
    async def fail_ann(self, symbol: str, limit: int = 20):
        raise ProviderUnavailable("公告源超时")

    async def ok_news(self, symbol: str, name: str = "", limit: int = 20):
        return [make_item("article")]

    monkeypatch.setattr(EastmoneyAnnouncementProvider, "fetch", fail_ann)
    monkeypatch.setattr(EastmoneyNewsSearchProvider, "fetch", ok_news)

    data = await get_company_news(FakeRedis(), "600519")

    assert data.partial is True
    assert data.announcements == []
    assert len(data.articles) == 1


async def test_both_sources_fail_raises(monkeypatch: pytest.MonkeyPatch):
    async def fail(self, symbol: str, name: str = "", limit: int = 20):
        raise ProviderUnavailable("超时")

    monkeypatch.setattr(EastmoneyAnnouncementProvider, "fetch", fail)
    monkeypatch.setattr(EastmoneyNewsSearchProvider, "fetch", fail)

    from app.providers.base import MarketUnavailable

    with pytest.raises(MarketUnavailable):
        await get_company_news(FakeRedis(), "600519")


async def test_both_sources_empty_returns_empty(monkeypatch: pytest.MonkeyPatch):
    async def empty(self, symbol: str, name: str = "", limit: int = 20):
        return []

    monkeypatch.setattr(EastmoneyAnnouncementProvider, "fetch", empty)
    monkeypatch.setattr(EastmoneyNewsSearchProvider, "fetch", empty)

    data = await get_company_news(FakeRedis(), "600519")

    assert data.partial is False
    assert data.announcements == []
    assert data.articles == []


class FakeMarketService:
    async def get_quote(self, code: str) -> Quote:
        return Quote(
            symbol=code,
            name="测试股份",
            price=10.0,
            source="fake",
            fetched_at=now_shanghai(),
        )


@pytest.fixture
async def client():
    redis = FakeRedis()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-1")
    app.dependency_overrides[stocks.get_redis] = lambda: redis
    app.dependency_overrides[stocks.get_market_service] = lambda: FakeMarketService()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_news_endpoint(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def fake_news(redis, symbol, *, name="", limit=20):
        return CompanyNewsData(
            symbol=symbol,
            announcements=[make_item("announcement")][:limit],
            articles=[make_item("article")][:limit],
            fetched_at=now_shanghai(),
        )

    monkeypatch.setattr(stocks, "get_company_news", fake_news)

    response = await client.get("/api/v1/stocks/600519/news", params={"limit": 5})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["symbol"] == "600519"
    assert len(body["announcements"]) == 1


async def test_fund_flow_endpoint(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def fake_flow(redis, symbol):
        return FundFlowData(
            symbol=symbol,
            days=[
                FundFlowDay(
                    date="2026-10-21",
                    main_net=1.2e8,
                    main_pct=5.6,
                    close=10.5,
                    change_pct=1.2,
                )
            ],
            fetched_at=now_shanghai(),
        )

    monkeypatch.setattr(stocks, "get_fund_flow", fake_flow)

    response = await client.get("/api/v1/stocks/600519/fund-flow")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["symbol"] == "600519"
    assert body["days"][0]["main_net"] == 120000000.0


async def test_fund_flow_invalid_symbol(client: AsyncClient):
    response = await client.get("/api/v1/stocks/bad/fund-flow")

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_SYMBOL"


async def test_fund_flow_unavailable(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def empty_flow(redis, symbol):
        return None

    monkeypatch.setattr(stocks, "get_fund_flow", empty_flow)

    response = await client.get("/api/v1/stocks/600519/fund-flow")

    assert response.status_code == 503
    assert response.json()["code"] == "MARKET_UNAVAILABLE"


async def test_ai_search_cooldown(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    calls = {"count": 0}

    async def fake_search(redis, quote, *, cache_seconds=None):
        calls["count"] += 1
        return WebSearchResult(
            query="测试",
            success=True,
            pages=[
                WebSource(
                    title="测试资讯",
                    url="https://example.com/1",
                    date="2026-10-21",
                )
            ],
            fetched_at=now_shanghai(),
        )

    monkeypatch.setattr(stocks, "search_symbol_web", fake_search)

    first = await client.post("/api/v1/stocks/600519/news/ai-search")
    second = await client.post("/api/v1/stocks/600519/news/ai-search")

    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert second.json()["code"] == "RATE_LIMITED"
    assert calls["count"] == 1

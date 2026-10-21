"""元宝搜索解析、缓存、官方 TC3 与未配置测试（不访问外网）。"""

import json
from datetime import UTC, datetime

import httpx

from app.core.config import settings
from app.providers.base import now_shanghai
from app.providers.models import Quote
from app.schemas.search import WebSearchResult, WebSource
from app.services.web_search_service import (
    YuanbaoSearchClient,
    search_symbol_web,
)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


class FakeSearchClient:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query: str) -> WebSearchResult:
        self.calls += 1
        return WebSearchResult(
            query=query,
            success=True,
            pages=[
                WebSource(
                    title="测试公告",
                    url="https://example.com/notice",
                    date="2026-10-21",
                    site="测试站点",
                    summary="公司发布公告。",
                )
            ],
            fetched_at=now_shanghai(),
        )


def make_quote() -> Quote:
    return Quote(
        symbol="600519",
        name="贵州茅台",
        price=1315.0,
        source="tencent",
        fetched_at=now_shanghai(),
    )


def test_parse_pages_and_dedupe():
    raw = [
        json.dumps(
            {
                "title": "公告 A",
                "url": "https://example.com/a",
                "date": "2026-10-21",
                "site": "站点 A",
                "passage": "内容 A",
            }
        ),
        {
            "title": "公告 A 重复",
            "url": "https://example.com/a",
            "date": "2026-10-21",
            "site": "站点 A",
            "content": "重复内容",
        },
        {
            "title": "新闻 B",
            "url": "https://example.com/b",
            "date": "",
            "site": "站点 B",
            "content": "内容 B",
        },
        {"title": "", "url": "https://example.com/empty"},
    ]

    pages = YuanbaoSearchClient.parse_pages(raw)

    assert len(pages) == 2
    assert pages[0].title == "公告 A"
    assert pages[1].title == "新闻 B"
    assert pages[1].summary == "内容 B"


async def test_search_disabled_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "wsa_secret_id", "")
    monkeypatch.setattr(settings, "wsa_secret_key", "")
    monkeypatch.setattr(settings, "wsa_api_key", "")
    client = FakeSearchClient()

    result = await search_symbol_web(FakeRedis(), make_quote(), client=client)

    assert result.success is False
    assert "WSA_SECRET_ID" in (result.error or "")
    assert client.calls == 0


async def test_search_result_cached(monkeypatch):
    monkeypatch.setattr(settings, "wsa_api_key", "test-key")
    redis = FakeRedis()
    client = FakeSearchClient()
    quote = make_quote()

    first = await search_symbol_web(redis, quote, client=client)
    second = await search_symbol_web(redis, quote, client=client)

    assert first.success is True
    assert first.cached is False
    assert second.cached is True
    assert second.pages[0].title == "测试公告"
    assert client.calls == 1


def _official_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "wsa_secret_id", "AKIDtest")
    monkeypatch.setattr(settings, "wsa_secret_key", "test-secret")
    monkeypatch.setattr(settings, "wsa_secret_token", "")
    monkeypatch.setattr(settings, "wsa_api_key", "")
    monkeypatch.setattr(settings, "wsa_search_host", "wsa.tencentcloudapi.com")
    monkeypatch.setattr(settings, "wsa_search_version", "2025-05-08")
    monkeypatch.setattr(settings, "wsa_search_freshness", "m3")


async def test_official_mode_signs_tc3_request(monkeypatch):
    _official_settings(monkeypatch)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "Response": {
                    "Query": "贵州茅台 600519",
                    "Pages": [
                        json.dumps(
                            {
                                "title": "官方接口返回",
                                "url": "https://example.com/official",
                                "date": "2026-10-20",
                                "passage": "公告摘要",
                                "site": "测试站点",
                            }
                        )
                    ],
                    "Version": "flagship",
                    "RequestId": "req-1",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await YuanbaoSearchClient(http_client=http_client).search("贵州茅台 600519")

    assert result.success is True
    assert result.pages[0].title == "官方接口返回"
    assert result.version == "flagship"

    request = captured[0]
    assert str(request.url) == "https://wsa.tencentcloudapi.com/"
    assert request.headers["X-TC-Action"] == "SearchPro"
    assert request.headers["X-TC-Version"] == "2025-05-08"
    assert "x-tc-token" not in request.headers

    timestamp = int(request.headers["X-TC-Timestamp"])
    date = datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%d")
    authorization = request.headers["Authorization"]
    assert authorization.startswith(
        f"TC3-HMAC-SHA256 Credential=AKIDtest/{date}/wsa/tc3_request, "
        "SignedHeaders=content-type;host, Signature="
    )
    signature = authorization.rsplit("Signature=", 1)[1]
    assert len(signature) == 64
    int(signature, 16)

    payload = json.loads(request.content)
    assert payload["Query"] == "贵州茅台 600519"
    assert payload["Mode"] == 0
    assert payload["Industry"] == "finance"
    assert payload["Cnt"] in (10, 20, 30, 40, 50)
    assert payload["Freshness"] == "m3"
    assert "Action" not in payload


async def test_official_mode_maps_response_error(monkeypatch):
    _official_settings(monkeypatch)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Response": {
                    "Error": {
                        "Code": "ResourceNotFound",
                        "Message": "用户资源未开通。",
                    },
                    "RequestId": "req-2",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await YuanbaoSearchClient(http_client=http_client).search("测试")

    assert result.success is False
    assert "未开通" in (result.error or "")


async def test_bearer_mode_keeps_bearer_and_skips_freshness(monkeypatch):
    monkeypatch.setattr(settings, "wsa_secret_id", "")
    monkeypatch.setattr(settings, "wsa_secret_key", "")
    monkeypatch.setattr(settings, "wsa_api_key", "test-key")
    monkeypatch.setattr(settings, "wsa_search_url", "https://api.wsa.example.com/SearchPro")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"Pages": [], "Msg": "无结果", "Version": "lite"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await YuanbaoSearchClient(http_client=http_client).search("测试")

    assert result.success is False
    assert result.error == "无结果"
    request = captured[0]
    assert request.headers["Authorization"] == "Bearer test-key"
    assert "X-TC-Action" not in request.headers
    payload = json.loads(request.content)
    assert "Freshness" not in payload


async def test_secret_id_in_api_key_field_is_rejected_before_request(monkeypatch):
    monkeypatch.setattr(settings, "wsa_secret_id", "")
    monkeypatch.setattr(settings, "wsa_secret_key", "")
    monkeypatch.setattr(settings, "wsa_api_key", "AKIDexampleSecretId0000000000000000")
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"Pages": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await YuanbaoSearchClient(http_client=http_client).search("测试")

    assert result.success is False
    assert "SecretId" in (result.error or "")
    assert "WSA_SECRET_KEY" in (result.error or "")
    assert calls == 0

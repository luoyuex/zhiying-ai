"""代理池与出站路由测试：入口解析、失败分类、换出口与回落直连。"""

import asyncio
import time
from uuid import uuid4

import httpx
import pytest

from app.db.redis import get_redis
from app.providers.base import ProviderUnavailable
from app.providers.egress import EgressRouter, classify_response, provider_for_url
from app.providers.proxy_pool import (
    ApiProxyPool,
    FailureKind,
    ProxyEndpoint,
    ProxyHealthStore,
    ProxyPool,
    ProxySelector,
    parse_api_payload,
    parse_proxy_endpoints,
)

MARKET_URL = "https://push2.eastmoney.com/api/qt/stock/get"


def test_parse_proxy_endpoints_supports_bare_and_socks():
    endpoints = parse_proxy_endpoints(
        "1.2.3.4:8080, socks5://user:pass@5.6.7.8:1080\nhttp://u:p@9.9.9.9:3128",
        rotates=True,
    )

    assert [item.display for item in endpoints] == [
        "http://1.2.3.4:8080",
        "socks5://5.6.7.8:1080",
        "http://9.9.9.9:3128",
    ]
    assert all(item.rotates for item in endpoints)


def test_parse_proxy_endpoints_dedupes_and_skips_invalid():
    endpoints = parse_proxy_endpoints(
        "http://a:b@1.2.3.4:8080, http://c:d@1.2.3.4:8080, "
        "ftp://5.6.7.8:21, noport",
        rotates=False,
    )

    assert len(endpoints) == 1
    assert endpoints[0].display == "http://1.2.3.4:8080"


def test_endpoint_display_hides_credentials():
    endpoint = ProxyEndpoint("http://user:secret@1.2.3.4:8080")

    assert endpoint.display == "http://1.2.3.4:8080"
    assert "secret" not in endpoint.id


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://push2.eastmoney.com/api/qt/stock/get", "eastmoney"),
        ("https://datacenter.eastmoney.com/api/data/v1/get", "eastmoney"),
        ("https://qt.gtimg.cn/q=sh600519", "tencent"),
        ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", "tencent"),
        ("https://hq.sinajs.cn/list=sh600519", "sina"),
        ("https://quotes.sina.cn/cn/api/jsonp.php", "sina"),
        ("https://finance.sina.com.cn/realstock/company", "sina"),
        ("https://wsa.tencentcloudapi.com/SearchPro", None),
        ("https://api.deepseek.com/v1/chat/completions", None),
    ],
)
def test_provider_for_url(url: str, expected: str | None):
    assert provider_for_url(url) == expected


@pytest.mark.parametrize(
    ("status", "content", "headers", "expected"),
    [
        (200, b'{"data":1}', {}, None),
        (200, b"", {}, FailureKind.BANNED),
        (403, b"", {}, FailureKind.BANNED),
        (429, b"", {}, FailureKind.BANNED),
        (407, b"", {}, FailureKind.DEAD),
        (502, b"", {}, FailureKind.UPSTREAM),
        (
            200,
            "<html><title>请输入验证码</title></html>".encode(),
            {"content-type": "text/html; charset=utf-8"},
            FailureKind.BANNED,
        ),
        (
            200,
            "<html><body>正常公告页面</body></html>".encode(),
            {"content-type": "text/html; charset=utf-8"},
            None,
        ),
    ],
)
def test_classify_response(status: int, content: bytes, headers: dict, expected):
    response = httpx.Response(
        status,
        content=content,
        headers=headers,
        request=httpx.Request("GET", MARKET_URL),
    )

    assert classify_response(response) is expected


class MemoryHealthStore:
    def __init__(self) -> None:
        self.cooldowns: dict[str, float] = {}
        self.bans: dict[tuple[str, str], float] = {}
        self.soft: dict[str, int] = {}
        self.successes: list[tuple[str, float]] = []

    async def cooldown_remaining(self, endpoint_id: str, provider: str) -> float:
        now = time.time()
        return max(
            self.cooldowns.get(endpoint_id, 0.0) - now,
            self.bans.get((endpoint_id, provider), 0.0) - now,
            0.0,
        )

    async def score(self, endpoint_id: str) -> float:
        return 1.0

    async def mark_used(self, endpoint_id: str) -> None:
        return None

    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        self.successes.append((endpoint_id, latency_ms))

    async def record_soft_failure(self, endpoint_id: str) -> None:
        self.soft[endpoint_id] = self.soft.get(endpoint_id, 0) + 1

    async def record_failure(
        self,
        endpoint_id: str,
        kind: FailureKind,
        *,
        provider: str,
        cooldown_seconds: int,
        ban_seconds: int,
    ) -> None:
        now = time.time()
        if kind is FailureKind.DEAD:
            self.cooldowns[endpoint_id] = now + cooldown_seconds
        elif kind is FailureKind.BANNED:
            self.bans[(endpoint_id, provider)] = now + ban_seconds


async def test_pool_bans_endpoint_for_the_provider_only():
    endpoint = ProxyEndpoint("http://1.2.3.4:8080", rotates=False)
    store = MemoryHealthStore()
    pool = ProxyPool(
        [endpoint],
        store,
        ProxySelector(store),
        cooldown_seconds=60,
        ban_seconds=900,
    )

    await pool.report_failure(endpoint, "eastmoney", FailureKind.BANNED)

    assert await pool.acquire("eastmoney") is None
    assert await pool.acquire("tencent") is endpoint


async def test_rotating_tunnel_is_not_cooled_after_site_ban():
    endpoint = ProxyEndpoint("http://1.2.3.4:8080", rotates=True)
    store = MemoryHealthStore()
    pool = ProxyPool(
        [endpoint],
        store,
        ProxySelector(store),
        cooldown_seconds=60,
        ban_seconds=900,
    )

    await pool.report_failure(endpoint, "eastmoney", FailureKind.BANNED)

    assert await pool.acquire("eastmoney") is endpoint
    assert store.soft[endpoint.id] == 1


async def test_dead_endpoint_is_cooled_for_all_providers():
    endpoint = ProxyEndpoint("http://1.2.3.4:8080", rotates=True)
    store = MemoryHealthStore()
    pool = ProxyPool(
        [endpoint],
        store,
        ProxySelector(store),
        cooldown_seconds=60,
        ban_seconds=900,
    )

    await pool.report_failure(endpoint, "eastmoney", FailureKind.DEAD)

    assert await pool.acquire("eastmoney") is None
    assert await pool.acquire("tencent") is None


def test_parse_api_payload_success():
    payload = {
        "code": 0,
        "success": "true",
        "msg": "",
        "data": [
            {
                "IP": "203.0.113.10",
                "Port": 3828,
                "IpAddress": "测试地区",
            }
        ],
    }

    endpoints = parse_api_payload(payload)

    assert len(endpoints) == 1
    assert endpoints[0].url == "http://203.0.113.10:3828"
    assert endpoints[0].rotates is False
    assert endpoints[0].dynamic is True


def test_parse_api_payload_rejects_invalid():
    assert parse_api_payload({"code": 1, "msg": "提取过快", "data": []}) == []
    assert parse_api_payload({"code": 0, "data": [{"IP": "bad", "Port": 1}]}) == []
    assert parse_api_payload({"code": 0, "data": [{"IP": "1.2.3.4", "Port": 0}]}) == []
    assert parse_api_payload({"code": 0, "data": []}) == []


class FakeApiSource:
    def __init__(self, batches: list[list[ProxyEndpoint]]) -> None:
        self.batches = batches
        self.calls = 0
        self.closed = False

    async def fetch(self) -> list[ProxyEndpoint]:
        index = min(self.calls, len(self.batches) - 1)
        self.calls += 1
        return self.batches[index]

    async def aclose(self) -> None:
        self.closed = True


def make_api_pool(source: FakeApiSource, *, ttl: int = 60) -> ApiProxyPool:
    return ApiProxyPool(
        source,
        ttl_seconds=ttl,
        error_cooldown_seconds=0,
    )


async def test_api_pool_replaces_ip_on_ban():
    first = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    second = ProxyEndpoint("http://2.2.2.2:8080", rotates=False)
    source = FakeApiSource([[first], [second]])
    pool = make_api_pool(source)

    assert await pool.acquire("eastmoney") == first
    await pool.report_failure(first, "eastmoney", FailureKind.BANNED)

    assert await pool.acquire("eastmoney", {first.id}) == second
    assert source.calls == 2


async def test_api_pool_keeps_ip_on_upstream():
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    source = FakeApiSource([[endpoint]])
    pool = make_api_pool(source)

    assert await pool.acquire("eastmoney") == endpoint
    await pool.report_failure(endpoint, "eastmoney", FailureKind.UPSTREAM)

    # 目标站问题本次不再提取；下个请求仍复用同一个 IP
    assert await pool.acquire("eastmoney", {endpoint.id}) is None
    assert source.calls == 1
    assert await pool.acquire("tencent") == endpoint


async def test_api_pool_refreshes_after_ttl():
    first = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    second = ProxyEndpoint("http://2.2.2.2:8080", rotates=False)
    source = FakeApiSource([[first], [second]])
    pool = make_api_pool(source, ttl=0)

    assert await pool.acquire("eastmoney") == first
    assert await pool.acquire("eastmoney") == second
    assert source.calls == 2


async def test_api_pool_reuses_within_ttl():
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    source = FakeApiSource([[endpoint]])
    pool = make_api_pool(source, ttl=60)

    assert await pool.acquire("eastmoney") == endpoint
    assert await pool.acquire("tencent") == endpoint
    assert source.calls == 1


async def test_api_pool_does_not_refresh_without_request():
    first = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    second = ProxyEndpoint("http://2.2.2.2:8080", rotates=False)
    source = FakeApiSource([[first], [second]])
    pool = make_api_pool(source, ttl=0)

    assert await pool.acquire("eastmoney") == first
    await asyncio.sleep(0.05)
    # 没有新请求就不在后台提取
    assert source.calls == 1
    assert await pool.acquire("eastmoney") == second
    assert source.calls == 2


async def test_api_pool_concurrent_requests_extract_once():
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    source = FakeApiSource([[endpoint]])
    pool = make_api_pool(source, ttl=60)

    results = await asyncio.gather(
        pool.acquire("eastmoney"), pool.acquire("tencent")
    )

    assert results == [endpoint, endpoint]
    assert source.calls == 1


async def test_api_pool_returns_none_when_extraction_fails():
    source = FakeApiSource([[]])
    pool = ApiProxyPool(
        source,
        ttl_seconds=60,
        error_cooldown_seconds=60,
    )

    assert await pool.acquire("eastmoney") is None
    assert source.calls == 1
    # 错误冷却期内不重复提取
    assert await pool.acquire("eastmoney") is None
    assert source.calls == 1


class FakePool:
    def __init__(self, endpoints: list[ProxyEndpoint]) -> None:
        self.endpoints = endpoints
        self.acquire_calls: list[tuple[str, set[str]]] = []
        self.failures: list[tuple[str, str, FailureKind]] = []
        self.successes: list[tuple[str, float]] = []

    async def acquire(
        self, provider: str, exclude: set[str] | None = None
    ) -> ProxyEndpoint | None:
        excluded = set(exclude or set())
        self.acquire_calls.append((provider, excluded))
        for endpoint in self.endpoints:
            if endpoint.id not in excluded:
                return endpoint
        return None

    async def report_success(self, endpoint: ProxyEndpoint, latency_ms: float) -> None:
        self.successes.append((endpoint.id, latency_ms))

    async def report_failure(
        self, endpoint: ProxyEndpoint, provider: str, kind: FailureKind
    ) -> None:
        self.failures.append((endpoint.id, provider, kind))


class FakeClientCache:
    def __init__(self, clients: dict[str, httpx.AsyncClient]) -> None:
        self._clients = clients
        self.closed = False

    def get(self, endpoint: ProxyEndpoint) -> httpx.AsyncClient:
        return self._clients[endpoint.id]

    async def aclose(self) -> None:
        self.closed = True


class AlwaysAllow:
    async def allow(self, provider: str, endpoint_id: str) -> bool:
        return True


@pytest.fixture
async def client_factory():
    created: list[httpx.AsyncClient] = []

    def factory(handler) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        created.append(client)
        return client

    yield factory

    for client in created:
        await client.aclose()


def make_router(
    pool: FakePool,
    cache: FakeClientCache,
    direct: httpx.AsyncClient,
    *,
    max_attempts: int = 2,
    providers: set[str] | None = None,
    limiter=None,
) -> EgressRouter:
    return EgressRouter(
        direct_client=lambda: direct,
        pool=pool,
        client_cache=cache,
        limiter=limiter or AlwaysAllow(),
        max_attempts=max_attempts,
        proxy_providers=providers,
    )


async def test_router_switches_to_second_endpoint_on_403(client_factory):
    first = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    second = ProxyEndpoint("http://2.2.2.2:8080", rotates=False)
    pool = FakePool([first, second])
    cache = FakeClientCache(
        {
            first.id: client_factory(
                lambda request: httpx.Response(403, request=request)
            ),
            second.id: client_factory(
                lambda request: httpx.Response(
                    200, content=b'{"ok":1}', request=request
                )
            ),
        }
    )
    direct = client_factory(
        lambda request: httpx.Response(500, request=request)
    )
    router = make_router(pool, cache, direct)

    response = await router.fetch(MARKET_URL)

    assert response.status_code == 200
    assert response.json() == {"ok": 1}
    assert pool.failures == [(first.id, "eastmoney", FailureKind.BANNED)]
    assert [endpoint_id for endpoint_id, _ in pool.successes] == [second.id]


async def test_router_retries_rotating_tunnel_on_403(client_factory):
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=True)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(403, request=request)
        return httpx.Response(200, content=b"ok", request=request)

    pool = FakePool([endpoint])
    router = make_router(
        pool,
        FakeClientCache({endpoint.id: client_factory(handler)}),
        client_factory(lambda request: httpx.Response(500, request=request)),
    )

    response = await router.fetch("https://qt.gtimg.cn/q=sh600519")

    assert response.text == "ok"
    assert calls["count"] == 2


async def test_router_falls_back_to_direct_when_pool_exhausted(client_factory):
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    pool = FakePool([endpoint])
    direct_calls = {"count": 0}

    def direct_handler(request: httpx.Request) -> httpx.Response:
        direct_calls["count"] += 1
        return httpx.Response(200, content=b"direct", request=request)

    router = make_router(
        pool,
        FakeClientCache(
            {
                endpoint.id: client_factory(
                    lambda request: httpx.Response(503, request=request)
                )
            }
        ),
        client_factory(direct_handler),
    )

    response = await router.fetch(MARKET_URL)

    assert response.text == "direct"
    assert direct_calls["count"] == 1
    # 5xx 是目标站问题，代理不冷却，只是本轮换掉
    assert pool.failures == [(endpoint.id, "eastmoney", FailureKind.UPSTREAM)]


async def test_rotating_tunnel_target_reset_is_upstream(client_factory):
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=True)

    def reset_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("Server disconnected", request=request)

    pool = FakePool([endpoint])
    router = make_router(
        pool,
        FakeClientCache({endpoint.id: client_factory(reset_handler)}),
        client_factory(
            lambda request: httpx.Response(200, content=b"direct", request=request)
        ),
    )

    response = await router.fetch(MARKET_URL)

    assert response.text == "direct"
    # 目标站断开不冷却整个隧道入口，用下一个出口重试一次
    assert pool.failures == [
        (endpoint.id, "eastmoney", FailureKind.UPSTREAM),
        (endpoint.id, "eastmoney", FailureKind.UPSTREAM),
    ]


async def test_rotating_tunnel_retries_upstream_on_next_ip(client_factory):
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=True)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, content=b"ok", request=request)

    pool = FakePool([endpoint])
    router = make_router(
        pool,
        FakeClientCache({endpoint.id: client_factory(handler)}),
        client_factory(lambda request: httpx.Response(500, request=request)),
    )

    response = await router.fetch(MARKET_URL)

    assert response.text == "ok"
    assert calls["count"] == 2
    assert pool.failures == [(endpoint.id, "eastmoney", FailureKind.UPSTREAM)]


async def test_non_rotating_pool_target_reset_is_dead(client_factory):
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)

    def reset_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("Server disconnected", request=request)

    pool = FakePool([endpoint])
    router = make_router(
        pool,
        FakeClientCache({endpoint.id: client_factory(reset_handler)}),
        client_factory(
            lambda request: httpx.Response(200, content=b"direct", request=request)
        ),
    )

    await router.fetch(MARKET_URL)

    assert pool.failures == [(endpoint.id, "eastmoney", FailureKind.DEAD)]


async def test_dynamic_endpoint_target_reset_is_upstream(client_factory):
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=False, dynamic=True)

    def reset_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("Server disconnected", request=request)

    pool = FakePool([endpoint])
    router = make_router(
        pool,
        FakeClientCache({endpoint.id: client_factory(reset_handler)}),
        client_factory(
            lambda request: httpx.Response(200, content=b"direct", request=request)
        ),
    )

    response = await router.fetch(MARKET_URL)

    assert response.text == "direct"
    # 提取的 IP 遇到目标站断开不应丢弃，保留到 TTL
    assert pool.failures == [(endpoint.id, "eastmoney", FailureKind.UPSTREAM)]


async def test_rotating_tunnel_connect_error_is_dead(client_factory):
    endpoint = ProxyEndpoint("http://1.1.1.1:8080", rotates=True)

    def connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    pool = FakePool([endpoint])
    router = make_router(
        pool,
        FakeClientCache({endpoint.id: client_factory(connect_error)}),
        client_factory(
            lambda request: httpx.Response(200, content=b"direct", request=request)
        ),
    )

    await router.fetch(MARKET_URL)

    # 连不上入口才是真正的 DEAD
    assert pool.failures == [(endpoint.id, "eastmoney", FailureKind.DEAD)]


async def test_non_market_host_and_filtered_provider_bypass_pool(client_factory):
    endpoint = ProxyEndpoint("http://1.1.1.1:8080")
    direct = client_factory(
        lambda request: httpx.Response(200, content=b"direct", request=request)
    )

    pool = FakePool([endpoint])
    router = make_router(pool, FakeClientCache({}), direct)
    response = await router.fetch("https://wsa.tencentcloudapi.com/SearchPro")
    assert response.text == "direct"
    assert pool.acquire_calls == []

    filtered_pool = FakePool([endpoint])
    filtered = make_router(
        filtered_pool,
        FakeClientCache({}),
        direct,
        providers={"tencent"},
    )
    await filtered.fetch(MARKET_URL)
    assert filtered_pool.acquire_calls == []


async def test_router_skips_endpoint_denied_by_per_endpoint_limiter(client_factory):
    first = ProxyEndpoint("http://1.1.1.1:8080", rotates=False)
    second = ProxyEndpoint("http://2.2.2.2:8080", rotates=False)
    pool = FakePool([first, second])
    cache = FakeClientCache(
        {
            first.id: client_factory(
                lambda request: httpx.Response(200, content=b"first", request=request)
            ),
            second.id: client_factory(
                lambda request: httpx.Response(200, content=b"second", request=request)
            ),
        }
    )

    class DenyFirst:
        def __init__(self) -> None:
            self.calls = 0

        async def allow(self, provider: str, endpoint_id: str) -> bool:
            self.calls += 1
            return self.calls > 1

    router = make_router(
        pool,
        cache,
        client_factory(lambda request: httpx.Response(500, request=request)),
        limiter=DenyFirst(),
    )

    response = await router.fetch(MARKET_URL)

    assert response.text == "second"
    assert pool.failures == []


async def test_redis_health_store_cools_dead_and_bans_per_provider():
    redis = get_redis()
    store = ProxyHealthStore(redis)
    dead_id = f"test-dead-{uuid4().hex[:8]}"
    banned_id = f"test-banned-{uuid4().hex[:8]}"
    keys = [
        f"mkt:proxy:{dead_id}",
        f"mkt:proxy:{dead_id}:ban:eastmoney",
        f"mkt:proxy:{banned_id}",
        f"mkt:proxy:{banned_id}:ban:eastmoney",
    ]
    try:
        await store.record_failure(
            dead_id,
            FailureKind.DEAD,
            provider="eastmoney",
            cooldown_seconds=60,
            ban_seconds=900,
        )
        assert await store.cooldown_remaining(dead_id, "eastmoney") > 0
        assert await store.cooldown_remaining(dead_id, "tencent") > 0

        await store.record_failure(
            banned_id,
            FailureKind.BANNED,
            provider="eastmoney",
            cooldown_seconds=60,
            ban_seconds=900,
        )
        assert await store.cooldown_remaining(banned_id, "eastmoney") > 0
        assert await store.cooldown_remaining(banned_id, "tencent") == 0

        await store.record_success(banned_id, 120)
        assert await store.score(banned_id) > 0
    finally:
        await redis.delete(*keys)


async def test_fetch_rejects_empty_body(monkeypatch):
    from app.providers import http as http_module

    class EmptyRouter:
        async def fetch(self, url, *, params=None, headers=None):
            return httpx.Response(
                200, content=b"", request=httpx.Request("GET", url)
            )

    monkeypatch.setattr(http_module, "_router", EmptyRouter())

    with pytest.raises(ProviderUnavailable, match="响应体为空"):
        await http_module.fetch("https://qt.gtimg.cn/q=sh600519")

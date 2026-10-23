"""行情出站路由：按 URL 域名决定直连还是走代理，并负责失败分类与换出口。

只代理行情源（东财/腾讯/新浪）；元宝搜索、LLM 等有独立鉴权与配额的请求直连。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis import get_redis
from app.providers.base import ProviderRateLimited
from app.providers.proxy_pool import (
    ApiProxyPool,
    ApiProxySource,
    FailureKind,
    ProxyEndpoint,
    ProxyHealthStore,
    ProxyPool,
    ProxyPoolProtocol,
    ProxySelector,
    parse_proxy_endpoints,
)
from app.providers.resilience import TokenBucket

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}

_PROVIDER_HOSTS = (
    ("eastmoney.com", "eastmoney"),
    ("gtimg.cn", "tencent"),
    ("sina.com.cn", "sina"),
    ("sina.cn", "sina"),
    ("sinajs.cn", "sina"),
)

_CAPTCHA_MARKERS = ("请输入验证码", "访问过于频繁", "安全验证", "人机验证", "captcha")

# 目标站在已建立隧道后断开/读超时：对旋转隧道是单次出口或目标站问题，不代表入口坏了
_TARGET_TRANSPORT_ERRORS: tuple[type[Exception], ...] = (
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.WriteError,
)


def classify_transport_error(
    exc: httpx.HTTPError, endpoint: ProxyEndpoint
) -> FailureKind:
    if (endpoint.rotates or endpoint.dynamic) and isinstance(
        exc, _TARGET_TRANSPORT_ERRORS
    ):
        return FailureKind.UPSTREAM
    return FailureKind.DEAD


def provider_for_url(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    for domain, provider in _PROVIDER_HOSTS:
        if host == domain or host.endswith("." + domain):
            return provider
    return None


def _looks_like_captcha(response: httpx.Response) -> bool:
    if "html" not in response.headers.get("content-type", "").lower():
        return False
    try:
        text = response.text[:2000].lower()
    except Exception:  # noqa: BLE001
        return False
    return any(marker in text for marker in _CAPTCHA_MARKERS)


def classify_response(response: httpx.Response) -> FailureKind | None:
    """None 表示可用；403/429/空 body/验证码页按目标站封禁处理。"""
    status = response.status_code
    if status == 407:
        return FailureKind.DEAD
    if status in (403, 429):
        return FailureKind.BANNED
    if status >= 500:
        return FailureKind.UPSTREAM
    if not response.content.strip():
        return FailureKind.BANNED
    if _looks_like_captcha(response):
        return FailureKind.BANNED
    return None


class ProxyClientCache:
    """每个代理入口一个 AsyncClient。

    隧道入口（rotates=True）禁用 keep-alive：快代理等隧道按连接切换出口 IP，
    复用连接会固定在一个 IP 上。静态池仍保持 keep-alive 以复用连接。
    """

    def __init__(self, *, timeout: float, connect_timeout: float = 3.0) -> None:
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._timeout = timeout
        self._connect_timeout = connect_timeout

    def get(self, endpoint: ProxyEndpoint) -> httpx.AsyncClient:
        client = self._clients.get(endpoint.id)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                proxy=endpoint.url,
                timeout=httpx.Timeout(self._timeout, connect=self._connect_timeout),
                headers=DEFAULT_HEADERS,
                follow_redirects=True,
                trust_env=False,
                limits=httpx.Limits(
                    max_keepalive_connections=0 if endpoint.rotates else 20
                ),
            )
            self._clients[endpoint.id] = client
        return client

    async def aclose(self) -> None:
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()


class EndpointRateLimiter:
    """单出口令牌桶，key 为 mkt:tb:{provider}:{endpoint_id}。"""

    def __init__(self, *, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._buckets: dict[str, TokenBucket] = {}

    async def allow(self, provider: str, endpoint_id: str) -> bool:
        if self._rate <= 0:
            return True
        name = f"{provider}:{endpoint_id}"
        bucket = self._buckets.get(name)
        if bucket is None:
            bucket = TokenBucket(get_redis(), self._rate, self._burst, name)
            self._buckets[name] = bucket
        try:
            # 短暂等待而不是立刻放弃：否则桶一空就把流量打回直连，
            # 既绕过限速又暴露服务器出口 IP。
            await bucket.acquire()
        except ProviderRateLimited:
            return False
        return True


class EgressRouter:
    def __init__(
        self,
        *,
        direct_client: Callable[[], httpx.AsyncClient],
        pool: ProxyPoolProtocol | None = None,
        client_cache: ProxyClientCache | None = None,
        limiter: EndpointRateLimiter | None = None,
        max_attempts: int = 2,
        proxy_providers: set[str] | None = None,
    ) -> None:
        self._direct_client = direct_client
        self._pool = pool
        # 代理请求必须早于 provider 超时失败，否则外层 asyncio.timeout
        # 会直接取消 fetch，路由层没机会标记坏 IP 并换 IP 重试
        proxy_timeout = max(
            2.0,
            min(
                settings.market_http_timeout,
                settings.market_provider_timeout - 1.5,
            ),
        )
        self._clients = client_cache or ProxyClientCache(
            timeout=proxy_timeout, connect_timeout=2.0
        )
        self._limiter = limiter or EndpointRateLimiter(
            rate=settings.egress_proxy_per_ip_rate,
            burst=settings.egress_proxy_per_ip_burst,
        )
        self._max_attempts = max(1, max_attempts)
        self._proxy_providers = proxy_providers or set()
        self._confirmed: set[tuple[str, str]] = set()

    async def fetch(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        provider = provider_for_url(url)
        if (
            self._pool is None
            or provider is None
            or (self._proxy_providers and provider not in self._proxy_providers)
        ):
            return await self._direct_client().get(url, params=params, headers=headers)
        return await self._fetch_via_pool(
            url, provider, params=params, headers=headers
        )

    async def _fetch_via_pool(
        self,
        url: str,
        provider: str,
        *,
        params: dict | None,
        headers: dict | None,
    ) -> httpx.Response:
        assert self._pool is not None
        exclude: set[str] = set()
        last_reason = "no_available_proxy"

        for attempt in range(1, self._max_attempts + 1):
            endpoint = await self._pool.acquire(provider, exclude)
            if endpoint is None:
                break

            if not await self._limiter.allow(provider, endpoint.id):
                exclude.add(endpoint.id)
                last_reason = "rate_limited"
                continue

            try:
                client = self._clients.get(endpoint)
            except Exception as exc:  # noqa: BLE001 - 如 socks5 缺少 socksio
                await self._pool.report_failure(endpoint, provider, FailureKind.DEAD)
                exclude.add(endpoint.id)
                last_reason = f"client_init_failed: {exc}"
                logger.warning(
                    "代理客户端创建失败 proxy=%s provider=%s: %s",
                    endpoint.display,
                    provider,
                    exc,
                )
                continue

            started = time.perf_counter()
            try:
                response = await client.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                kind = classify_transport_error(exc, endpoint)
                await self._pool.report_failure(endpoint, provider, kind)
                # 隧道入口会换 IP：目标站断开时换一个出口再试
                if not (endpoint.rotates and kind is FailureKind.UPSTREAM):
                    exclude.add(endpoint.id)
                last_reason = f"transport_{kind.value}: {exc}"
                logger.warning(
                    "代理请求失败 proxy=%s provider=%s reason=%s attempt=%d: %s",
                    endpoint.display,
                    provider,
                    kind.value,
                    attempt,
                    exc,
                )
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            kind = classify_response(response)
            if kind is not None:
                await self._pool.report_failure(endpoint, provider, kind)
                # 隧道入口背后会换 IP：封禁/目标站异常都只重试，不把入口从本轮排除
                if not (
                    endpoint.rotates
                    and kind in (FailureKind.BANNED, FailureKind.UPSTREAM)
                ):
                    exclude.add(endpoint.id)
                last_reason = f"http_{response.status_code}_{kind.value}"
                logger.warning(
                    "代理请求异常 proxy=%s provider=%s reason=%s status=%d attempt=%d",
                    endpoint.display,
                    provider,
                    kind.value,
                    response.status_code,
                    attempt,
                )
                continue

            await self._pool.report_success(endpoint, latency_ms)
            confirmed = (endpoint.id, provider)
            if confirmed not in self._confirmed:
                self._confirmed.add(confirmed)
                logger.info(
                    "代理出口已确认可用 proxy=%s provider=%s latency=%.0fms",
                    endpoint.display,
                    provider,
                    latency_ms,
                )
            logger.debug(
                "代理请求成功 proxy=%s provider=%s latency=%.0fms",
                endpoint.display,
                provider,
                latency_ms,
            )
            return response

        logger.info(
            "代理池无可用出口，回落直连 provider=%s reason=%s", provider, last_reason
        )
        return await self._direct_client().get(url, params=params, headers=headers)

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
        await self._clients.aclose()


def build_router(direct_client: Callable[[], httpx.AsyncClient]) -> EgressRouter:
    if not settings.egress_proxy_enabled:
        return EgressRouter(direct_client=direct_client)

    if settings.egress_proxy_source == "api":
        if not settings.egress_proxy_api_url:
            logger.warning(
                "EGRESS_PROXY_SOURCE=api 但未配置 EGRESS_PROXY_API_URL，行情将直连"
            )
            return EgressRouter(direct_client=direct_client)
        pool = ApiProxyPool(
            ApiProxySource(settings.egress_proxy_api_url, timeout=5.0),
            ttl_seconds=settings.egress_proxy_api_ttl_seconds,
            error_cooldown_seconds=settings.egress_proxy_api_error_cooldown_seconds,
        )
        logger.info(
            "行情代理池已启用 | source=api per_process=true ttl=%ss providers=%s",
            settings.egress_proxy_api_ttl_seconds,
            settings.egress_proxy_providers or "all",
        )
        return EgressRouter(
            direct_client=direct_client,
            pool=pool,
            max_attempts=settings.egress_proxy_max_attempts,
            proxy_providers=settings.egress_proxy_provider_set,
        )

    endpoints = parse_proxy_endpoints(
        settings.egress_proxy_entries,
        rotates=settings.egress_proxy_rotate_per_request,
    )
    if not endpoints:
        logger.warning(
            "已开启 EGRESS_PROXY_ENABLED 但未配置代理入口，行情将直连"
        )
        return EgressRouter(direct_client=direct_client)

    store = ProxyHealthStore(get_redis())
    pool = ProxyPool(
        endpoints,
        store,
        ProxySelector(store),
        cooldown_seconds=settings.egress_proxy_cooldown_seconds,
        ban_seconds=settings.egress_proxy_ban_seconds,
    )
    logger.info(
        "行情代理池已启用 | source=static endpoints=%d rotate_per_request=%s providers=%s",
        len(endpoints),
        settings.egress_proxy_rotate_per_request,
        settings.egress_proxy_providers or "all",
    )
    return EgressRouter(
        direct_client=direct_client,
        pool=pool,
        max_attempts=settings.egress_proxy_max_attempts,
        proxy_providers=settings.egress_proxy_provider_set,
    )

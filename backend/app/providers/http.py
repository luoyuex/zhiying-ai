"""Provider 共用的 HTTP 客户端、出站路由与全局并发闸门。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import ProviderUnavailable
from app.providers.egress import DEFAULT_HEADERS, EgressRouter, build_router

logger = get_logger(__name__)

_direct_client: httpx.AsyncClient | None = None
_router: EgressRouter | None = None
_semaphore: asyncio.Semaphore | None = None


def get_http_client() -> httpx.AsyncClient:
    """直连通道：WSA / LLM 等非行情请求，以及代理全挂时的回落出口。"""
    global _direct_client
    if _direct_client is None or _direct_client.is_closed:
        _direct_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.market_http_timeout, connect=3.0),
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            # 代理池关闭时保留旧的全局代理语义；开启后由 EgressRouter 按行情域名分流，
            # 直连通道不再挂代理，避免把元宝搜索也送进代理池。
            proxy=None
            if settings.egress_proxy_enabled
            else (settings.egress_proxy_url or None),
            # 不继承 shell/IDE 里的 HTTP(S)_PROXY：
            # 本机代理一旦换端口（如开发工具每次会话分配临时端口），
            # 长驻进程就会连到失效端口，表现为全源 "All connection attempts failed"。
            trust_env=False,
        )
    return _direct_client


def _get_router() -> EgressRouter:
    global _router
    if _router is None:
        _router = build_router(get_http_client)
    return _router


async def close_http_client() -> None:
    global _direct_client, _router
    if _router is not None:
        await _router.aclose()
        _router = None
    if _direct_client is not None and not _direct_client.is_closed:
        await _direct_client.aclose()
    _direct_client = None


async def fetch(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    """统一的出站请求：网络错误与 4xx/5xx 转成 ProviderUnavailable。"""
    try:
        response = await _get_router().fetch(url, params=params, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"{url}: {exc}") from exc
    # 行情源被封时经常返回 200 + 空 body；不识别会被当成「无数据」静默吞掉
    if not response.content.strip():
        raise ProviderUnavailable(f"{url}: 响应体为空（可能被目标站拦截）")
    return response


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.market_global_concurrency)
    return _semaphore


@asynccontextmanager
async def provider_slot() -> AsyncIterator[None]:
    """所有出站行情请求共用一个全局信号量，避免免费源被封。"""
    async with _get_semaphore():
        yield

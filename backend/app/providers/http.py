"""Provider 共用的 HTTP 客户端与全局并发闸门。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import ProviderUnavailable

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

_client: httpx.AsyncClient | None = None
_semaphore: asyncio.Semaphore | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.market_http_timeout, connect=3.0),
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            follow_redirects=True,
            proxy=settings.egress_proxy_url or None,
            trust_env=not settings.egress_proxy_url,
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def fetch(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    """统一的出站请求：网络错误与 4xx/5xx 转成 ProviderUnavailable。"""
    try:
        response = await get_http_client().get(url, params=params, headers=headers)
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"{url}: {exc}") from exc


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

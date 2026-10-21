"""Provider 注册表：按能力维护降级链，统一加上限流、熔断、超时与并发闸门。"""

import asyncio

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import (
    CircuitOpenError,
    DataNotFound,
    MarketUnavailable,
    ProviderError,
    ProviderRateLimited,
    ProviderUnavailable,
    UnsupportedCapability,
)
from app.providers.eastmoney import EastmoneyProvider
from app.providers.http import provider_slot
from app.providers.models import Adjust, KlinePeriod, KlineSeries, Quote
from app.providers.resilience import CircuitBreaker, TokenBucket
from app.providers.sina import SinaProvider
from app.providers.symbols import StockSymbol
from app.providers.tencent import TencentProvider

logger = get_logger(__name__)

# Provider 级全局限速：rate（每秒补令牌）、burst（桶容量）
PROVIDER_RATE_LIMITS: dict[str, tuple[float, int]] = {
    "tencent": (5.0, 10),
    "sina": (3.0, 6),
    "eastmoney": (5.0, 10),
}


class ProviderRegistry:
    def __init__(
        self,
        redis: Redis,
        *,
        providers: dict[str, list] | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._providers = providers or {
            "quote": [TencentProvider(), SinaProvider(), EastmoneyProvider()],
            "kline": [EastmoneyProvider(), TencentProvider(), SinaProvider()],
        }
        self._buckets = {
            name: TokenBucket(redis, rate, burst, name)
            for name, (rate, burst) in PROVIDER_RATE_LIMITS.items()
        }
        self._breaker = breaker or CircuitBreaker(
            redis,
            failures=settings.market_circuit_failures,
            window_seconds=settings.market_circuit_window_seconds,
            open_seconds=settings.market_circuit_open_seconds,
        )

    async def quote(self, symbol: StockSymbol) -> Quote:
        return await self._call("quote", symbol)

    async def kline(
        self,
        symbol: StockSymbol,
        period: KlinePeriod,
        adjust: Adjust,
        limit: int,
    ) -> KlineSeries:
        return await self._call(
            "kline", symbol, period=period, adjust=adjust, limit=limit
        )

    async def _call(self, capability: str, symbol: StockSymbol, **kwargs):
        chain = self._providers.get(capability, [])
        errors: list[Exception] = []

        for provider in chain:
            name = provider.name
            try:
                await self._breaker.ensure_closed(name, capability)
                bucket = self._buckets.get(name)
                if bucket is not None:
                    await bucket.acquire()
                async with provider_slot():
                    async with asyncio.timeout(settings.market_provider_timeout):
                        result = await getattr(provider, capability)(symbol, **kwargs)
                await self._breaker.record_success(name, capability)
                return result
            except (CircuitOpenError, ProviderRateLimited, UnsupportedCapability) as exc:
                errors.append(exc)
            except DataNotFound as exc:
                errors.append(exc)
            except TimeoutError:
                await self._breaker.record_failure(name, capability)
                errors.append(ProviderUnavailable(f"{name}.{capability} 超时"))
                logger.warning("行情源超时: %s.%s", name, capability)
            except ProviderError as exc:
                await self._breaker.record_failure(name, capability)
                errors.append(exc)
                logger.warning("行情源失败: %s.%s: %s", name, capability, exc)
            except Exception as exc:  # noqa: BLE001 - 单源异常不能拖垮整条链
                await self._breaker.record_failure(name, capability)
                errors.append(exc)
                logger.exception("行情源未捕获异常: %s.%s", name, capability)

        if errors and all(isinstance(exc, DataNotFound) for exc in errors):
            raise DataNotFound(f"所有行情源均无 {symbol.code} 数据") from errors[-1]
        raise MarketUnavailable(capability, errors)

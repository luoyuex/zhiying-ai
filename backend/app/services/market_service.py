"""行情服务：统一缓存、请求合并、降级与 stale 兜底。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from redis.asyncio import Redis

from app.core.config import settings
from app.providers.base import DataNotFound, MarketUnavailable
from app.providers.models import Adjust, KlinePeriod, KlineSeries, Quote
from app.providers.registry import ProviderRegistry
from app.providers.resilience import MarketCache, SingleFlight
from app.providers.symbols import parse_symbol

TModel = TypeVar("TModel", Quote, KlineSeries)

# singleflight 必须跨请求共享，否则不同请求各发一次
_SINGLEFLIGHT = SingleFlight()


class MarketDataService:
    def __init__(
        self,
        redis: Redis,
        *,
        registry: ProviderRegistry | None = None,
        cache: MarketCache | None = None,
        quote_fresh_seconds: int | None = None,
        quote_stale_seconds: int | None = None,
        kline_fresh_seconds: int | None = None,
        kline_stale_seconds: int | None = None,
    ) -> None:
        self._registry = registry or ProviderRegistry(redis)
        self._cache = cache or MarketCache(redis)
        self._quote_fresh = (
            quote_fresh_seconds
            if quote_fresh_seconds is not None
            else settings.market_quote_fresh_seconds
        )
        self._quote_stale = (
            quote_stale_seconds
            if quote_stale_seconds is not None
            else settings.market_quote_stale_seconds
        )
        self._kline_fresh = (
            kline_fresh_seconds
            if kline_fresh_seconds is not None
            else settings.market_kline_fresh_seconds
        )
        self._kline_stale = (
            kline_stale_seconds
            if kline_stale_seconds is not None
            else settings.market_kline_stale_seconds
        )

    async def get_quote(self, code: str) -> Quote:
        symbol = parse_symbol(code)
        return await self._cached(
            key=f"quote:{symbol.code}",
            model=Quote,
            fresh_seconds=self._quote_fresh,
            stale_seconds=self._quote_stale,
            factory=lambda: self._registry.quote(symbol),
        )

    async def prime_quotes(self, quotes: dict[str, Quote]) -> None:
        """把批量接口拿到的报价写进缓存，后续 get_quote 可直接命中。"""
        if not quotes:
            return
        await asyncio.gather(
            *(
                self._cache.set(
                    f"quote:{code}", quote.model_dump(mode="json"), self._quote_stale
                )
                for code, quote in quotes.items()
            ),
            return_exceptions=True,
        )

    async def get_kline(
        self,
        code: str,
        *,
        period: KlinePeriod = KlinePeriod.DAY,
        adjust: Adjust = Adjust.QFQ,
        limit: int = 250,
    ) -> KlineSeries:
        if not 1 <= limit <= 800:
            raise ValueError("limit 必须在 1~800 之间")
        symbol = parse_symbol(code)
        return await self._cached(
            key=f"kline:{symbol.code}:{period.value}:{adjust.value}:{limit}",
            model=KlineSeries,
            fresh_seconds=self._kline_fresh,
            stale_seconds=self._kline_stale,
            factory=lambda: self._registry.kline(
                symbol, period=period, adjust=adjust, limit=limit
            ),
        )

    async def _cached(
        self,
        *,
        key: str,
        model: type[TModel],
        fresh_seconds: int,
        stale_seconds: int,
        factory: Callable[[], Awaitable[TModel]],
    ) -> TModel:
        cached = await self._cache.get(key)
        if cached is not None and cached.age_seconds <= fresh_seconds:
            return model.model_validate(cached.payload)

        try:
            result = await _SINGLEFLIGHT.run(key, factory)
        except (DataNotFound, MarketUnavailable):
            if cached is not None:
                return model.model_validate(cached.payload).model_copy(
                    update={"delayed": True}
                )
            raise

        await self._cache.set(key, result.model_dump(mode="json"), stale_seconds)
        return result

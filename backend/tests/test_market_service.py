"""MarketDataService 抗压行为测试：缓存、singleflight、熔断、stale 兜底。"""

import asyncio

import pytest
from redis.asyncio import Redis

from app.db.redis import get_redis
from app.providers.base import MarketUnavailable, ProviderUnavailable, now_shanghai
from app.providers.models import Quote
from app.providers.registry import ProviderRegistry
from app.providers.resilience import CircuitBreaker, MarketCache
from app.providers.symbols import StockSymbol
from app.services.market_service import MarketDataService


class FakeQuoteProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.delay = 0.0

    async def quote(self, symbol: StockSymbol) -> Quote:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ProviderUnavailable("fake 数据源故障")
        return Quote(
            symbol=symbol.code,
            name="测试股份",
            price=10.0,
            source=self.name,
            fetched_at=now_shanghai(),
        )


def build_service(
    redis: Redis,
    provider: FakeQuoteProvider,
    *,
    fresh: int,
    stale: int = 60,
    failures: int = 5,
) -> MarketDataService:
    breaker = CircuitBreaker(
        redis, failures=failures, window_seconds=60, open_seconds=60
    )
    registry = ProviderRegistry(
        redis, providers={"quote": [provider]}, breaker=breaker
    )
    return MarketDataService(
        redis,
        registry=registry,
        cache=MarketCache(redis),
        quote_fresh_seconds=fresh,
        quote_stale_seconds=stale,
    )


@pytest.fixture
async def clean_market_keys():
    redis = get_redis()

    async def cleanup() -> None:
        for pattern in (
            "mkt:cache:quote:6006*",
            "mkt:cache:kline:6006*",
            "mkt:cb:fake:*",
        ):
            keys = [key async for key in redis.scan_iter(pattern)]
            if keys:
                await redis.delete(*keys)

    await cleanup()
    yield
    await cleanup()


async def test_fresh_cache_avoids_second_call(clean_market_keys):
    redis = get_redis()
    provider = FakeQuoteProvider()
    service = build_service(redis, provider, fresh=60)

    first = await service.get_quote("600600")
    second = await service.get_quote("600600")

    assert provider.calls == 1
    assert first.price == second.price == 10.0
    assert first.delayed is False


async def test_stale_cache_returned_when_all_sources_fail(clean_market_keys):
    redis = get_redis()
    provider = FakeQuoteProvider()
    service = build_service(redis, provider, fresh=0, stale=60)

    fresh_quote = await service.get_quote("600601")
    assert fresh_quote.delayed is False

    provider.fail = True
    stale_quote = await service.get_quote("600601")

    assert provider.calls == 2
    assert stale_quote.delayed is True
    assert stale_quote.fetched_at == fresh_quote.fetched_at


async def test_singleflight_merges_concurrent_requests(clean_market_keys):
    redis = get_redis()
    provider = FakeQuoteProvider()
    provider.delay = 0.1
    service = build_service(redis, provider, fresh=0)

    results = await asyncio.gather(
        *[service.get_quote("600602") for _ in range(10)]
    )

    assert provider.calls == 1
    assert all(quote.symbol == "600602" for quote in results)


async def test_circuit_breaker_skips_after_threshold(clean_market_keys):
    redis = get_redis()
    provider = FakeQuoteProvider()
    provider.fail = True
    service = build_service(redis, provider, fresh=0, failures=2)

    for _ in range(2):
        with pytest.raises(MarketUnavailable):
            await service.get_quote("600603")

    with pytest.raises(MarketUnavailable):
        await service.get_quote("600603")

    assert provider.calls == 2

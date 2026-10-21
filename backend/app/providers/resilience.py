"""行情抗压组件：缓存、请求合并、令牌桶、熔断。

全部基于 Redis 做跨请求共享；Redis 故障时降级为「放行」，避免缓存层拖垮行情。
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from math import ceil
from typing import TypeVar

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.providers.base import CircuitOpenError, ProviderRateLimited
from app.providers.models import CachedPayload

logger = get_logger(__name__)

T = TypeVar("T")


class MarketCache:
    PREFIX = "mkt:cache:"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> CachedPayload | None:
        try:
            raw = await self._redis.get(self.PREFIX + key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取行情缓存失败: %s", exc)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            age = max(time.time() - float(data["cached_at"]), 0.0)
            return CachedPayload(payload=data["payload"], age_seconds=age)
        except (ValueError, KeyError, TypeError):
            return None

    async def set(self, key: str, payload: dict, ttl_seconds: int) -> None:
        body = json.dumps(
            {"payload": payload, "cached_at": time.time()},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            await self._redis.set(self.PREFIX + key, body, ex=ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("写入行情缓存失败: %s", exc)


class SingleFlight:
    """同一个 key 的并发请求只真正发起一次。"""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    async def run(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        task = self._tasks.get(key)
        if task is None:
            task = asyncio.create_task(factory())
            self._tasks[key] = task
            task.add_done_callback(lambda done, k=key: self._finish(k, done))
        return await asyncio.shield(task)

    def _finish(self, key: str, task: asyncio.Task) -> None:
        if self._tasks.get(key) is task:
            self._tasks.pop(key, None)
        if not task.cancelled():
            task.exception()  # 消费异常，避免无人等待时告警


class TokenBucket:
    """Redis 令牌桶，按 Provider 全局限速。"""

    _LUA = """
    local burst = tonumber(ARGV[1])
    local rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
    local tokens = tonumber(data[1])
    local ts = tonumber(data[2])
    if tokens == nil then tokens = burst end
    if ts == nil then ts = now end
    tokens = math.min(burst, tokens + math.max(0, now - ts) * rate)
    if tokens < 1 then
        redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
        redis.call('EXPIRE', KEYS[1], 60)
        return 0
    end
    tokens = tokens - 1
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
    redis.call('EXPIRE', KEYS[1], 60)
    return 1
    """

    def __init__(self, redis: Redis, rate: float, burst: int, name: str) -> None:
        self._redis = redis
        self._rate = rate
        self._burst = burst
        self._key = f"mkt:tb:{name}"

    async def acquire(self, timeout: float = 0.8) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            try:
                allowed = await self._redis.eval(
                    self._LUA, 1, self._key, self._burst, self._rate, time.time()
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("令牌桶不可用，放行: %s", exc)
                return
            if int(allowed) == 1:
                return
            if loop.time() >= deadline:
                raise ProviderRateLimited(f"{self._key} 本地限流")
            await asyncio.sleep(0.05)


class CircuitBreaker:
    """按 provider + capability 统计失败；打开后 60s 内直接跳过。"""

    _FAIL_LUA = """
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local open_for = tonumber(ARGV[3])
    local threshold = tonumber(ARGV[4])
    local data = redis.call('HMGET', KEYS[1], 'failures', 'window_start', 'open_until')
    local failures = tonumber(data[1]) or 0
    local window_start = tonumber(data[2]) or now
    local open_until = tonumber(data[3]) or 0
    if now < open_until then return open_until end
    if now - window_start > window then
        failures = 0
        window_start = now
    end
    failures = failures + 1
    if failures >= threshold then open_until = now + open_for end
    redis.call('HSET', KEYS[1], 'failures', failures,
        'window_start', window_start, 'open_until', open_until)
    redis.call('EXPIRE', KEYS[1], math.max(window, open_for) + 60)
    return open_until
    """

    def __init__(
        self,
        redis: Redis,
        *,
        failures: int,
        window_seconds: int,
        open_seconds: int,
    ) -> None:
        self._redis = redis
        self._failures = failures
        self._window = window_seconds
        self._open_for = open_seconds

    @staticmethod
    def _key(provider: str, capability: str) -> str:
        return f"mkt:cb:{provider}:{capability}"

    async def ensure_closed(self, provider: str, capability: str) -> None:
        try:
            open_until = await self._redis.hget(self._key(provider, capability), "open_until")
        except Exception as exc:  # noqa: BLE001
            logger.warning("熔断器不可用，放行: %s", exc)
            return
        remaining = float(open_until or 0) - time.time()
        if remaining > 0:
            raise CircuitOpenError(provider, capability, ceil(remaining))

    async def record_success(self, provider: str, capability: str) -> None:
        try:
            await self._redis.delete(self._key(provider, capability))
        except Exception as exc:  # noqa: BLE001
            logger.warning("清理熔断器失败: %s", exc)

    async def record_failure(self, provider: str, capability: str) -> None:
        try:
            open_until = await self._redis.eval(
                self._FAIL_LUA,
                1,
                self._key(provider, capability),
                time.time(),
                self._window,
                self._open_for,
                self._failures,
            )
            if float(open_until or 0) > time.time():
                logger.warning("%s.%s 熔断打开 %ss", provider, capability, self._open_for)
        except Exception as exc:  # noqa: BLE001
            logger.warning("记录熔断失败: %s", exc)

"""热门股票服务：成交额榜 + Redis 缓存，刷新失败时回退过期副本。

首页每次打开都会读，缓存 5 分钟；东财短暂限流时用上一份榜单，避免入口闪空。
"""

import json
import time

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.providers.base import ProviderError
from app.providers.hot_stocks import EastmoneyHotStocksProvider, TencentHotStocksProvider
from app.schemas.stock import HotStockItem

logger = get_logger(__name__)

HOT_CACHE_KEY = "mkt:hot_stocks"
HOT_CACHE_TTL = 300
HOT_STALE_TTL = 86400
HOT_LIMIT = 8


async def _read_cache(redis: Redis) -> tuple[list[HotStockItem], float]:
    try:
        raw = await redis.get(HOT_CACHE_KEY)
    except Exception as exc:  # noqa: BLE001 - 缓存故障不影响取数
        logger.warning("读取热门股票缓存失败: %s", exc)
        return [], 0.0
    if not raw:
        return [], 0.0
    try:
        payload = json.loads(raw)
        items = [HotStockItem.model_validate(item) for item in payload.get("items") or []]
        return items, float(payload.get("fetched_at") or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("解析热门股票缓存失败: %s", exc)
        return [], 0.0


async def _fetch_live() -> list[HotStockItem]:
    """腾讯排行为主源；不可用时退东财，两者都失败才会抛错。"""
    try:
        return await TencentHotStocksProvider().fetch(limit=HOT_LIMIT)
    except ProviderError as exc:
        logger.warning("腾讯活跃榜不可用，改试东财: %s", exc)
    return await EastmoneyHotStocksProvider().fetch(limit=HOT_LIMIT)


async def load_hot_stocks(redis: Redis, limit: int = HOT_LIMIT) -> list[HotStockItem]:
    cached, cached_at = await _read_cache(redis)
    if cached and time.time() - cached_at < HOT_CACHE_TTL:
        return cached[:limit]

    try:
        items = await _fetch_live()
    except ProviderError as exc:
        if cached:
            logger.warning("热门股票刷新失败，使用过期缓存: %s", exc)
            return cached[:limit]
        raise

    try:
        await redis.set(
            HOT_CACHE_KEY,
            json.dumps(
                {
                    "items": [item.model_dump() for item in items],
                    "fetched_at": time.time(),
                },
                ensure_ascii=False,
            ),
            ex=HOT_STALE_TTL,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入热门股票缓存失败: %s", exc)
    return items[:limit]

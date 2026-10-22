"""个股公告与新闻聚合：并发取数、单源降级、Redis 缓存。"""

import asyncio

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import DataNotFound, MarketUnavailable, now_shanghai
from app.providers.news import (
    EastmoneyAnnouncementProvider,
    EastmoneyNewsSearchProvider,
)
from app.providers.symbols import parse_symbol
from app.schemas.news import CompanyNewsData

logger = get_logger(__name__)


def _slice(data: CompanyNewsData, limit: int) -> CompanyNewsData:
    return data.model_copy(
        update={
            "announcements": data.announcements[:limit],
            "articles": data.articles[:limit],
        }
    )


async def get_company_news(
    redis: Redis,
    symbol: str,
    *,
    name: str = "",
    limit: int = 20,
) -> CompanyNewsData:
    parsed = parse_symbol(symbol)
    key = f"mkt:news:{parsed.code}"

    try:
        cached = await redis.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取资讯缓存失败: %s", exc)
        cached = None
    if cached:
        try:
            return _slice(CompanyNewsData.model_validate_json(cached), limit)
        except ValueError:
            logger.warning("资讯缓存内容损坏 %s", parsed.code)

    announcements, articles = await asyncio.gather(
        EastmoneyAnnouncementProvider().fetch(parsed.code, limit=20),
        EastmoneyNewsSearchProvider().fetch(parsed.code, name=name, limit=20),
        return_exceptions=True,
    )

    failures = [
        exc
        for exc in (announcements, articles)
        if isinstance(exc, BaseException) and not isinstance(exc, DataNotFound)
    ]
    if len(failures) == 2:
        raise MarketUnavailable("news", failures)

    data = CompanyNewsData(
        symbol=parsed.code,
        announcements=[] if isinstance(announcements, BaseException) else announcements,
        articles=[] if isinstance(articles, BaseException) else articles,
        source="eastmoney_announcement+eastmoney_news",
        fetched_at=now_shanghai(),
        partial=bool(failures),
    )
    for exc in failures:
        logger.warning("获取资讯部分失败 %s: %s", parsed.code, exc)

    try:
        await redis.set(
            key,
            data.model_dump_json(),
            ex=settings.market_news_cache_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入资讯缓存失败: %s", exc)

    return _slice(data, limit)

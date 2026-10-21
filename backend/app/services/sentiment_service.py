"""市场情绪数据：ARBR（本地计算）+ 主要指数涨跌（东财）。"""

from app.core.logging import get_logger
from app.providers.base import now_shanghai
from app.providers.http import fetch
from app.providers.models import KlineBar, Quote
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.company import SentimentData

logger = get_logger(__name__)

_INDEX_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
_INDEX_SECIDS = "1.000001,0.399001"
_INDEX_FIELDS = "f2,f3,f12,f14"


def _arbr(bars: list[KlineBar], period: int = 26) -> tuple[float | None, float | None]:
    if len(bars) < period + 1:
        return None, None
    window = bars[-(period + 1) :]
    ar_up = 0.0
    ar_down = 0.0
    br_up = 0.0
    br_down = 0.0
    for index in range(1, len(window)):
        bar = window[index]
        prev_close = window[index - 1].close
        ar_up += max(bar.high - bar.open, 0)
        ar_down += max(bar.open - bar.low, 0)
        br_up += max(bar.high - prev_close, 0)
        br_down += max(prev_close - bar.low, 0)
    ar = round(ar_up / ar_down * 100, 2) if ar_down > 0 else None
    br = round(br_up / br_down * 100, 2) if br_down > 0 else None
    return ar, br


async def _index_changes(redis) -> dict[str, float]:
    cache_key = "mkt:index:cn"
    try:
        cached = await redis.get(cache_key)
        if cached:
            import json

            data = json.loads(cached)
            if isinstance(data, dict):
                return {str(key): float(value) for key, value in data.items()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取指数缓存失败: %s", exc)

    try:
        response = await fetch(
            _INDEX_URL,
            params={"secids": _INDEX_SECIDS, "fields": _INDEX_FIELDS},
        )
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("获取指数行情失败: %s", exc)
        return {}

    changes: dict[str, float] = {}
    for row in (payload.get("data") or {}).get("diff") or []:
        try:
            name = str(row.get("f14") or row.get("f12") or "")
            value = float(row.get("f3")) / 100
        except (TypeError, ValueError):
            continue
        if name:
            changes[name] = round(value, 2)

    if changes:
        try:
            import json

            await redis.set(cache_key, json.dumps(changes, ensure_ascii=False), ex=60)
        except Exception as exc:  # noqa: BLE001
            logger.warning("写入指数缓存失败: %s", exc)
    return changes


async def build_sentiment_data(
    redis,
    quote: Quote,
    bars: list[KlineBar],
    technical: TechnicalAnalysis,
) -> SentimentData:
    ar, br = _arbr(bars)
    index_changes = await _index_changes(redis)
    return SentimentData(
        symbol=quote.symbol,
        ar=ar,
        br=br,
        turnover_pct=quote.turnover_pct,
        volume_ratio=technical.indicators.volume_ratio,
        rsi14=technical.indicators.rsi14,
        index_changes=index_changes,
        fetched_at=now_shanghai(),
    )

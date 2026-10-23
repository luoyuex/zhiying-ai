"""腾讯批量报价：一次请求拿多只股票，自选股与选股共用。

单只 `get_quote` 走的是「降级链 + 缓存 + 单飞」的重链路，
一只一次请求；自选股上限 50 只时就会打出 50 个请求，容易打满令牌桶。
批量接口一次最多 50 只，正好把整页行情压到 1 个请求。
"""

from app.core.logging import get_logger
from app.providers.base import ProviderUnavailable
from app.providers.http import fetch, provider_slot
from app.providers.models import Quote
from app.providers.symbols import StockSymbol
from app.providers.tencent import TencentProvider

logger = get_logger(__name__)

QUOTE_BATCH_URL = "https://qt.gtimg.cn/q={}"
QUOTE_BATCH_SIZE = 50


async def fetch_quotes(symbols: list[StockSymbol]) -> dict[str, Quote]:
    """腾讯批量报价：一次最多 50 只，单只失败不影响整批。"""
    quotes: dict[str, Quote] = {}
    for start in range(0, len(symbols), QUOTE_BATCH_SIZE):
        chunk = symbols[start : start + QUOTE_BATCH_SIZE]
        query = ",".join(item.prefixed for item in chunk)
        try:
            async with provider_slot():
                response = await fetch(QUOTE_BATCH_URL.format(query))
        except ProviderUnavailable as exc:
            logger.warning("批量报价失败: %s", exc)
            continue
        for symbol in chunk:
            try:
                quotes[symbol.code] = TencentProvider.parse_quote(symbol, response.content)
            except Exception as exc:  # noqa: BLE001 - 停牌/无报价的股票跳过
                logger.info("批量报价解析失败 %s: %s", symbol.code, exc)
    return quotes

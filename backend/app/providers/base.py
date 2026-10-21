"""Provider 协议与异常。

Provider 只负责「取数 + 解析 + 标准化」，不做缓存、限流、降级；
这些横切能力由 registry / service 统一处理。
"""

from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from app.providers.models import Adjust, KlinePeriod, KlineSeries, Quote
from app.providers.symbols import StockSymbol

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


class ProviderError(Exception):
    """Provider 层的所有可预期异常基类。"""


class ProviderUnavailable(ProviderError):
    """网络错误、超时、5xx 等临时故障。"""


class ProviderSchemaDrift(ProviderError):
    """返回结构变化或字段缺失，解析失败。"""


class DataNotFound(ProviderError):
    """代码合法但数据源确实没有这只股票/这段数据。"""


class UnsupportedCapability(ProviderError):
    """该 Provider 不支持当前市场或周期。"""


class ProviderRateLimited(ProviderError):
    """本地令牌桶节流，未真正向远端发请求。"""


class CircuitOpenError(ProviderError):
    def __init__(self, provider: str, capability: str, retry_after: int) -> None:
        super().__init__(f"{provider}.{capability} 熔断中，{retry_after}s 后重试")
        self.provider = provider
        self.capability = capability
        self.retry_after = retry_after


class MarketUnavailable(ProviderError):
    """整条降级链都失败。"""

    def __init__(self, capability: str, errors: list[Exception]) -> None:
        self.capability = capability
        self.errors = errors
        super().__init__(f"行情源不可用（{capability}）：{errors}")


class QuoteProvider(Protocol):
    name: str

    async def quote(self, symbol: StockSymbol) -> Quote: ...


class KlineProvider(Protocol):
    name: str

    async def kline(
        self,
        symbol: StockSymbol,
        period: KlinePeriod,
        adjust: Adjust,
        limit: int,
    ) -> KlineSeries: ...


def now_shanghai() -> datetime:
    return datetime.now(TZ_SHANGHAI)


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "-", "--", "None", "null"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_datetime(raw: str) -> datetime | None:
    """解析行情里常见的几种时间字符串，失败返回 None。"""
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TZ_SHANGHAI)
        except ValueError:
            continue
    return None

"""行情统一模型。

约定（全项目唯一口径，Provider 不允许返回中文格式化文本）：
- 价格单位：元
- 成交量单位：股
- 成交额单位：元
- 时间：Asia/Shanghai 带时区
- 百分比字段以 ``_pct`` 结尾，值 1.23 表示 1.23%
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class KlinePeriod(StrEnum):
    MIN1 = "1m"
    MIN5 = "5m"
    MIN15 = "15m"
    MIN30 = "30m"
    MIN60 = "60m"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class Adjust(StrEnum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class Quote(BaseModel):
    symbol: str
    name: str
    price: float
    open: float | None = None
    pre_close: float | None = None
    high: float | None = None
    low: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume: float | None = Field(default=None, description="成交量，单位股")
    amount: float | None = Field(default=None, description="成交额，单位元")
    turnover_pct: float | None = None
    pe: float | None = Field(default=None, description="市盈率（动态）")
    pb: float | None = None
    total_market_cap: float | None = Field(default=None, description="总市值，单位元")
    float_market_cap: float | None = Field(default=None, description="流通市值，单位元")
    limit_up: float | None = None
    limit_down: float | None = None
    source: str
    fetched_at: datetime
    delayed: bool = Field(default=False, description="为 True 表示当前返回的是过期缓存")


class KlineBar(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(description="成交量，单位股")
    amount: float | None = None
    turnover_pct: float | None = None


class KlineSeries(BaseModel):
    symbol: str
    period: KlinePeriod
    adjust: Adjust
    bars: list[KlineBar]
    source: str
    fetched_at: datetime
    delayed: bool = False


class CachedPayload(BaseModel):
    payload: dict
    age_seconds: float


class StockBasic(BaseModel):
    """股票基础信息，用于建库与搜索，不含行情。"""

    code: str
    name: str
    exchange: str

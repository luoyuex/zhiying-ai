from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SignalDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class AnalysisSignal(BaseModel):
    name: str
    direction: SignalDirection
    detail: str


class IndicatorSnapshot(BaseModel):
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    rsi14: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_hist: float | None = None
    boll_upper: float | None = None
    boll_mid: float | None = None
    boll_lower: float | None = None
    atr14: float | None = None
    volume_ratio: float | None = None


class PriceLevels(BaseModel):
    entry: float
    take_profit: float
    stop_loss: float
    risk_reward: float
    support: float
    resistance: float
    computed_by: str = "code"


class TechnicalAnalysis(BaseModel):
    symbol: str
    name: str
    price: float
    as_of: datetime
    score: int = Field(ge=0, le=100)
    rating: str
    trend: str
    summary: str
    signals: list[AnalysisSignal]
    indicators: IndicatorSnapshot
    levels: PriceLevels
    source: str
    disclaimer: str = "技术指标由代码计算，仅供研究参考，不构成投资建议。"

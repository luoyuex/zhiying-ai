from datetime import datetime

from pydantic import BaseModel, Field


class FinancialMetric(BaseModel):
    report_date: str
    report_name: str = ""
    revenue: float | None = None
    revenue_growth_pct: float | None = None
    net_profit: float | None = None
    profit_growth_pct: float | None = None
    roe: float | None = None
    gross_margin_pct: float | None = None
    net_margin_pct: float | None = None
    debt_ratio_pct: float | None = None
    current_ratio: float | None = None
    eps: float | None = None
    bps: float | None = None


class FinancialData(BaseModel):
    symbol: str
    name: str = ""
    periods: list[FinancialMetric] = Field(default_factory=list)
    source: str = "eastmoney_finance"
    fetched_at: datetime


class FundFlowDay(BaseModel):
    date: str
    main_net: float | None = None
    small_net: float | None = None
    medium_net: float | None = None
    large_net: float | None = None
    super_large_net: float | None = None
    main_pct: float | None = None
    close: float | None = None
    change_pct: float | None = None


class FundFlowData(BaseModel):
    symbol: str
    days: list[FundFlowDay] = Field(default_factory=list)
    source: str = "eastmoney_fundflow"
    fetched_at: datetime


class SentimentData(BaseModel):
    symbol: str
    ar: float | None = None
    br: float | None = None
    turnover_pct: float | None = None
    volume_ratio: float | None = None
    rsi14: float | None = None
    index_changes: dict[str, float] = Field(default_factory=dict)
    source: str = "computed / eastmoney_index"
    fetched_at: datetime

"""选股结果与策略接口模型。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.ai import AIJobStatus

ScreenerStrategyId = Literal[
    "main_force", "low_price_bull", "small_cap", "profit_growth", "value_stock"
]


class FundFlowRankItem(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    # 超大单净流入（元）；新浪资金流排行口径
    main_net: float = 0.0
    main_net_pct: float | None = None
    amount: float | None = None


class PerformanceRow(BaseModel):
    symbol: str
    name: str
    report_date: str
    profit_growth: float | None = None
    revenue_growth: float | None = None
    industry: str = ""


class MainForceRecommendation(BaseModel):
    rank: int = 1
    symbol: str
    name: str = ""
    reasons: list[str] = Field(default_factory=list)
    highlights: str = ""
    risks: str = ""
    position: str = ""
    investment_period: str = ""

    @field_validator("reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip(" -•\t") for item in value.split("\n") if item.strip()]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            items = [str(value).strip()]
        return items[:6]

    @field_validator("highlights", "risks", "position", "investment_period", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return str(value or "").strip()[:300]


class MainForceAnalysisResponse(BaseModel):
    record_id: uuid.UUID | None = None
    strategy: str = "main_force"
    fund_flow: str = ""
    industry: str = ""
    fundamental: str = ""
    recommendations: list[MainForceRecommendation] = Field(default_factory=list)
    generated_at: datetime
    model: str
    quota_used: int = 0
    quota_limit: int = 0
    analyzed_count: int = 0
    source: str = "sina_fundflow+eastmoney_performance+tencent"
    disclaimer: str = (
        "AI 分析基于公开资金流、行业与财务数据，仅供研究参考，不构成投资建议。"
    )


class ScreenerRecordPick(BaseModel):
    rank: int = 1
    symbol: str
    name: str = ""


class MainForceRecordSummary(BaseModel):
    id: uuid.UUID
    strategy: str = "main_force"
    created_at: datetime
    analyzed_count: int = 0
    recommendation_count: int = 0
    final_n: int = 0
    max_change_pct: float | None = None
    picks: list[ScreenerRecordPick] = Field(default_factory=list)


class MainForceRecordDetail(BaseModel):
    id: uuid.UUID
    strategy: str = "main_force"
    created_at: datetime
    filters: dict = Field(default_factory=dict)
    result: MainForceAnalysisResponse


class ScreenerJobState(BaseModel):
    job_id: str
    strategy: str = "main_force"
    status: AIJobStatus
    phase: str = ""
    elapsed_seconds: int = 0
    error_code: str = ""
    error_message: str = ""
    record_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class LowPriceBullRequest(BaseModel):
    top_n: int = Field(default=5, ge=3, le=20)
    max_price: float = Field(default=10.0, gt=0, le=100)
    min_profit_growth: float = Field(default=100.0, ge=0)
    max_change_pct: float | None = Field(default=None, ge=-20, le=30)
    exclude_st: bool = True
    exclude_gem: bool = True
    exclude_star: bool = True
    exclude_bj: bool = True


class LowPriceBullAnalysisRequest(LowPriceBullRequest):
    final_n: int = Field(default=5, ge=3, le=10)


class LowPriceBullItem(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    amount: float | None = None
    profit_growth: float | None = None
    revenue_growth: float | None = None
    report_date: str = ""


class LowPriceBullResponse(BaseModel):
    strategy: str = "low_price_bull"
    items: list[LowPriceBullItem] = Field(default_factory=list)
    scanned_count: int = 0
    candidate_count: int = 0
    fetched_at: datetime
    source: str = "eastmoney_performance+tencent"
    filters: dict = Field(default_factory=dict)
    disclaimer: str = (
        "选股结果基于公开业绩数据、行情与规则筛选，仅供研究参考，不构成投资建议。"
    )


class SmallCapRequest(BaseModel):
    top_n: int = Field(default=5, ge=3, le=20)
    max_market_cap: float = Field(default=50.0, gt=0, le=500)
    min_profit_growth: float = Field(default=100.0, ge=0)
    min_revenue_growth: float = Field(default=10.0, ge=0)
    max_change_pct: float | None = Field(default=None, ge=-20, le=30)
    exclude_st: bool = True
    exclude_gem: bool = True
    exclude_star: bool = True
    exclude_bj: bool = True


class SmallCapAnalysisRequest(SmallCapRequest):
    final_n: int = Field(default=5, ge=3, le=10)


class ProfitGrowthAnalysisRequest(BaseModel):
    final_n: int = Field(default=5, ge=3, le=10)
    min_profit_growth: float = Field(default=10.0, ge=0)
    max_change_pct: float | None = Field(default=None, ge=-20, le=30)
    exclude_st: bool = True
    exclude_gem: bool = True
    exclude_star: bool = True
    exclude_bj: bool = True


class ProfitGrowthItem(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    amount: float | None = None
    profit_growth: float | None = None
    revenue_growth: float | None = None
    report_date: str = ""


class ValueStockAnalysisRequest(BaseModel):
    final_n: int = Field(default=5, ge=3, le=10)
    max_pe: float = Field(default=20.0, gt=0, le=200)
    max_pb: float = Field(default=1.5, gt=0, le=20)
    min_dividend_yield: float = Field(default=1.0, ge=0, le=20)
    max_debt_ratio: float = Field(default=30.0, ge=0, le=100)
    exclude_st: bool = True
    exclude_gem: bool = True
    exclude_star: bool = True
    exclude_bj: bool = True


class ValueStockItem(BaseModel):
    symbol: str
    name: str
    industry: str = ""
    price: float
    change_pct: float | None = None
    amount: float | None = None
    pe: float
    pb: float
    dividend_yield: float
    debt_ratio: float
    float_market_cap: float
    total_market_cap: float | None = None
    profit_growth: float | None = None
    revenue_growth: float | None = None
    report_date: str = ""


class SmallCapItem(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    total_market_cap: float | None = None
    profit_growth: float | None = None
    revenue_growth: float | None = None
    report_date: str = ""


class SmallCapResponse(BaseModel):
    strategy: str = "small_cap"
    items: list[SmallCapItem] = Field(default_factory=list)
    scanned_count: int = 0
    candidate_count: int = 0
    fetched_at: datetime
    source: str = "eastmoney_performance+tencent"
    filters: dict = Field(default_factory=dict)
    disclaimer: str = (
        "选股结果基于公开业绩数据、行情与规则筛选，仅供研究参考，不构成投资建议。"
    )


class ScreenerStrategy(BaseModel):
    id: str
    name: str
    description: str
    status: str = "available"


class MainForceScreenRequest(BaseModel):
    top_n: int = Field(default=10, ge=3, le=50)
    max_change_pct: float | None = Field(default=7.0, ge=-20, le=30)
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    exclude_st: bool = True
    exclude_gem: bool = True
    exclude_star: bool = True
    exclude_bj: bool = True


class MainForceAnalysisRequest(MainForceScreenRequest):
    final_n: int = Field(default=5, ge=3, le=10)


class MainForceScreenResponse(BaseModel):
    strategy: str = "main_force"
    items: list[FundFlowRankItem] = Field(default_factory=list)
    scanned_count: int = 0
    candidate_count: int = 0
    fetched_at: datetime
    source: str = "sina_fundflow"
    filters: dict = Field(default_factory=dict)
    disclaimer: str = (
        "选股结果基于公开资金流数据与简单规则筛选，仅供研究参考，不构成投资建议。"
    )

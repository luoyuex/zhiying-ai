"""选股结果与策略接口模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


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


class LowPriceBullRequest(BaseModel):
    top_n: int = Field(default=5, ge=3, le=20)
    max_price: float = Field(default=10.0, gt=0, le=100)
    min_profit_growth: float = Field(default=100.0, ge=0)
    max_change_pct: float | None = Field(default=None, ge=-20, le=30)
    exclude_st: bool = True
    exclude_gem: bool = True
    exclude_star: bool = True
    exclude_bj: bool = True


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

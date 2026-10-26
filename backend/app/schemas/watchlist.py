"""自选股接口模型。"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LatestAnalysis(BaseModel):
    report_id: str
    rating: str
    confidence: int
    decision_source: str
    position_action: str | None = None
    summary: str = ""
    rating_change: str | None = None
    prev_rating: str | None = None
    created_at: datetime


class WatchlistEntry(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    source: str = ""
    fetched_at: datetime | None = None
    delayed: bool = False
    added_at: datetime
    note: str = ""
    cost_price: float | None = None
    quantity: int | None = None
    latest: LatestAnalysis | None = None


class WatchlistAddRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    note: str = Field(default="", max_length=120)
    cost_price: float | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=0)


class WatchlistUpdateRequest(BaseModel):
    note: str | None = Field(default=None, max_length=120)
    cost_price: float | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=0)


class WatchlistAddResponse(BaseModel):
    symbol: str
    added: bool


class WatchlistStatus(BaseModel):
    symbol: str
    in_watchlist: bool


class WatchlistBatchRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=20)
    force: bool = False


class WatchlistBatchResult(BaseModel):
    symbol: str
    job_id: str | None = None
    status: str = "queued"
    error_code: str | None = None
    error_message: str | None = None


class PositionChangeEntry(BaseModel):
    id: str
    symbol: str
    old_cost_price: float | None = None
    new_cost_price: float | None = None
    old_quantity: int | None = None
    new_quantity: int | None = None
    created_at: datetime


class PriceAlertDirection(StrEnum):
    ABOVE = "above"
    BELOW = "below"


PriceAlertKind = Literal["custom", "entry", "take_profit", "stop_loss"]


class PriceAlertCreateRequest(BaseModel):
    # custom：手动涨到/跌破；其余类型由报告价位自动决定方向与目标价
    kind: PriceAlertKind = "custom"
    direction: Literal["above", "below"] | None = None
    target_price: float | None = Field(default=None, gt=0)
    report_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def require_fields(self) -> "PriceAlertCreateRequest":
        if self.kind == "custom":
            if self.direction is None or self.target_price is None:
                raise ValueError("自定义提醒必须填写方向和目标价")
        elif self.report_id is None:
            raise ValueError("从报告价位创建提醒时必须提供 report_id")
        return self


class PriceAlertView(BaseModel):
    id: str
    symbol: str
    name: str
    direction: str
    target_price: float
    kind: str = "custom"
    report_id: str | None = None
    status: str
    triggered_price: float | None = None
    triggered_at: datetime | None = None
    created_at: datetime

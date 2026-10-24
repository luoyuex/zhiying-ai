"""自选股接口模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


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


class PriceAlertCreateRequest(BaseModel):
    direction: Literal["above", "below"]
    target_price: float = Field(gt=0)


class PriceAlertView(BaseModel):
    id: str
    symbol: str
    name: str
    direction: str
    target_price: float
    status: str
    triggered_price: float | None = None
    triggered_at: datetime | None = None
    created_at: datetime

"""自选股接口模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class LatestAnalysis(BaseModel):
    report_id: str
    rating: str
    confidence: int
    decision_source: str
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

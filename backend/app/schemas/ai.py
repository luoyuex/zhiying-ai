from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.analyst import AnalystReport, FinalDecision, TeamDiscussion
from app.schemas.search import WebSource

RATING_ALIASES = {
    "看多": "看多",
    "强烈看多": "看多",
    "买入": "看多",
    "看涨": "看多",
    "偏多": "偏多",
    "谨慎看多": "偏多",
    "中性": "中性",
    "观望": "中性",
    "偏空": "偏空",
    "谨慎看空": "偏空",
    "看空": "看空",
    "卖出": "看空",
    "看跌": "看空",
}

TREND_ALIASES = {
    "上升": "上升",
    "上涨": "上升",
    "下降": "下降",
    "下跌": "下降",
    "震荡": "震荡",
    "盘整": "震荡",
    "中性": "震荡",
}


class AIAnalysisPayload(BaseModel):
    rating: Literal["看多", "偏多", "中性", "偏空", "看空"]
    confidence: int = Field(ge=0, le=100)
    trend: Literal["上升", "下降", "震荡"]
    summary: str = Field(min_length=1, max_length=600)
    key_points: list[str] = Field(default_factory=list, max_length=8)
    risks: list[str] = Field(default_factory=list, max_length=8)
    watch: str = Field(default="", max_length=300)

    @field_validator("rating", mode="before")
    @classmethod
    def normalize_rating(cls, value: object) -> str:
        text = str(value or "").strip().strip("。.!！ ")
        if text not in RATING_ALIASES:
            raise ValueError(f"rating 不合法：{text}")
        return RATING_ALIASES[text]

    @field_validator("trend", mode="before")
    @classmethod
    def normalize_trend(cls, value: object) -> str:
        text = str(value or "").strip().strip("。.!！ ")
        if text not in TREND_ALIASES:
            raise ValueError(f"trend 不合法：{text}")
        return TREND_ALIASES[text]

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: object) -> int:
        try:
            number = int(float(str(value).replace("%", "").strip()))
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence 必须是数字") from exc
        return max(0, min(100, number))

    @field_validator("key_points", "risks", mode="before")
    @classmethod
    def normalize_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = value.replace("\r", "").split("\n")
            items = [item.strip(" -•\t") for item in parts if item.strip()]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            items = [str(value).strip()]
        return items[:8]

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: object) -> str:
        return str(value or "").strip()[:600]

    @field_validator("watch", mode="before")
    @classmethod
    def normalize_watch(cls, value: object) -> str:
        return str(value or "").strip()[:300]


class AIAnalysisResponse(BaseModel):
    report_id: str | None = None
    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    model: str
    prompt_version: str
    generated_at: datetime
    data_as_of: datetime
    data_source: str
    cached: bool
    quota_used: int
    quota_limit: int
    analysis: AIAnalysisPayload
    analysts: list[AnalystReport] = Field(default_factory=list)
    decision: FinalDecision | None = None
    discussion: TeamDiscussion | None = None
    web_search_used: bool = False
    web_sources: list[WebSource] = Field(default_factory=list)
    disclaimer: str


class AIConfigResponse(BaseModel):
    configured: bool
    model: str
    prompt_version: str
    daily_quota: int
    quota_used: int


class AIJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AIJobState(BaseModel):
    job_id: str
    status: AIJobStatus
    symbol: str
    phase: str
    created_at: datetime
    updated_at: datetime
    elapsed_seconds: int = 0
    result: AIAnalysisResponse | None = None
    error_code: str | None = None
    error_message: str | None = None

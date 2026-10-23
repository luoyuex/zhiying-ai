"""组合 AI 诊断接口模型。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PositionAction = Literal["加仓", "建仓", "持有", "减仓", "清仓", "观望"]

_ACTION_ALIASES = {
    "加仓": "加仓",
    "增持": "加仓",
    "补仓": "加仓",
    "建仓": "建仓",
    "开仓": "建仓",
    "买入": "建仓",
    "持有": "持有",
    "继续持有": "持有",
    "减仓": "减仓",
    "减持": "减仓",
    "清仓": "清仓",
    "卖出": "清仓",
    "止损": "清仓",
    "观望": "观望",
    "等待": "观望",
}


def normalize_action(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return "观望"
    return _ACTION_ALIASES.get(text, "观望")


class PortfolioPositionAdvice(BaseModel):
    symbol: str
    name: str = ""
    action: PositionAction = "观望"
    reason: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action_field(cls, value: object) -> str:
        return normalize_action(value)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str:
        return str(value or "").strip()[:160]


class PortfolioDiagnosisDraft(BaseModel):
    health_score: int = 50
    summary: str = ""
    risk_notes: list[str] = Field(default_factory=list)
    allocation_advice: str = ""
    positions: list[PortfolioPositionAdvice] = Field(default_factory=list)

    @field_validator("health_score", mode="before")
    @classmethod
    def normalize_score(cls, value: object) -> int:
        try:
            number = int(float(str(value or "").replace("%", "").strip()))
        except (TypeError, ValueError):
            return 50
        return max(0, min(100, number))

    @field_validator("summary", "allocation_advice", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return str(value or "").strip()[:400]

    @field_validator("risk_notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip(" -•\t") for item in value.split("\n") if item.strip()]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            items = [str(value).strip()]
        return items[:5]


class PortfolioDiagnosisResponse(PortfolioDiagnosisDraft):
    id: uuid.UUID | None = None
    generated_at: datetime
    model: str
    quota_used: int = 0
    quota_limit: int = 0
    disclaimer: str = "组合诊断由 AI 基于自选股与持仓数据生成，仅供研究参考，不构成投资建议。"


class PortfolioDiagnosisSummary(BaseModel):
    id: uuid.UUID
    health_score: int
    position_count: int
    summary: str
    created_at: datetime


class PortfolioDiagnosisDetail(BaseModel):
    id: uuid.UUID
    created_at: datetime
    report: PortfolioDiagnosisResponse

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.analysis import PriceLevels

RATING_ALIASES = {
    "买入": "买入",
    "强烈买入": "买入",
    "增持": "买入",
    "持有": "持有",
    "中性": "持有",
    "观望": "持有",
    "卖出": "卖出",
    "强烈卖出": "卖出",
    "减持": "卖出",
}


class AnalystReport(BaseModel):
    key: str
    name: str
    score: int = Field(ge=0, le=100)
    rating: str
    summary: str
    points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class DecisionDraft(BaseModel):
    rating: Literal["买入", "持有", "卖出"]
    confidence: int = Field(ge=0, le=100)
    summary: str
    operation_advice: str
    holding_period: str
    position_size: str
    key_reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    risk_warning: str = ""
    consensus: list[str] = Field(default_factory=list)
    dissent: list[str] = Field(default_factory=list)

    @field_validator("rating", mode="before")
    @classmethod
    def normalize_rating(cls, value: object) -> str:
        text = str(value or "").strip().strip("。.!！ ")
        if text not in RATING_ALIASES:
            raise ValueError(f"rating 不合法：{text}")
        return RATING_ALIASES[text]

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: object) -> int:
        try:
            number = int(float(str(value).replace("%", "").strip()))
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence 必须是数字") from exc
        if 0 < number <= 10:
            number *= 10
        return max(0, min(100, number))

    @field_validator("key_reasons", "risks", "consensus", "dissent", mode="before")
    @classmethod
    def normalize_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip(" -•\t") for item in value.split("\n") if item.strip()]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            items = [str(value).strip()]
        return items[:8]

    @field_validator(
        "summary",
        "operation_advice",
        "holding_period",
        "position_size",
        "risk_warning",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return str(value or "").strip()[:600]


class FinalDecision(DecisionDraft):
    levels: PriceLevels
    decision_source: str = "llm"

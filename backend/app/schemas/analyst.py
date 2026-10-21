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
    # 该位分析师的最终稿来自 LLM 还是规则引擎；旧报告默认按规则版解读
    engine: Literal["rule", "llm"] = "rule"


class DiscussionTurn(BaseModel):
    speaker: str
    target: str = ""
    stance: Literal["同意", "补充", "质疑"] = "补充"
    content: str

    @field_validator("speaker", "target", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str:
        return str(value or "").strip().replace("分析师", "")[:16]

    @field_validator("stance", mode="before")
    @classmethod
    def normalize_stance(cls, value: object) -> str:
        text = str(value or "").strip()
        if text in {"同意", "认可", "支持", "赞同"}:
            return "同意"
        if text in {"质疑", "反对", "反驳", "异议"}:
            return "质疑"
        return "补充"

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value: object) -> str:
        return str(value or "").strip()[:240]


class TeamDiscussion(BaseModel):
    turns: list[DiscussionTurn] = Field(default_factory=list)
    summary: str = ""
    source: Literal["llm", "rule"] = "rule"

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: object) -> str:
        return str(value or "").strip()[:300]


class AnalystDraft(BaseModel):
    """LLM 分析师输出：只允许改结论，数据来源与缺口由系统补齐。"""

    # 缺失时保持 None，由服务层沿用规则稿分数，避免默认 50 覆盖有效结论
    score: int | None = None
    rating: str = ""
    summary: str = ""
    points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def normalize_score(cls, value: object) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            number = int(float(str(value).replace("分", "").strip()))
        except (TypeError, ValueError):
            return None
        return max(0, min(100, number))

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: object) -> str:
        return str(value or "").strip()[:600]

    @field_validator("rating", mode="before")
    @classmethod
    def normalize_rating_text(cls, value: object) -> str:
        return str(value or "").strip().strip("。.!！ ")[:16]

    @field_validator("points", "risks", mode="before")
    @classmethod
    def normalize_items(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip(" -•\t") for item in value.split("\n") if item.strip()]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            items = [str(value).strip()]
        return items[:6]


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
    # 结合用户持仓的动作建议；未自选/未提供持仓时为空
    position_action: Literal["加仓", "建仓", "持有", "减仓", "清仓", "观望"] | None = None
    position_advice: str = ""

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

    @field_validator("position_action", mode="before")
    @classmethod
    def normalize_position_action(cls, value: object) -> str | None:
        text = str(value or "").strip()
        if not text or text.lower() in {"none", "null", "nan"}:
            return None
        aliases = {
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
        return aliases.get(text)

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
        "position_advice",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return str(value or "").strip()[:600]


class FinalDecision(DecisionDraft):
    levels: PriceLevels
    decision_source: str = "llm"

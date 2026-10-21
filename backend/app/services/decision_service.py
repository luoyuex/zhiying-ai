"""首席策略官：一次 LLM 决策 + 规则兜底。"""

from typing import Any

from app.core.logging import get_logger
from app.llm.client import LLMClient, LLMError
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.providers.models import Quote
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.analyst import AnalystReport, DecisionDraft, FinalDecision, TeamDiscussion
from app.schemas.position import UserPosition
from app.schemas.search import WebSearchResult

logger = get_logger(__name__)

_WEIGHTS = {
    "technical": 0.25,
    "fundamental": 0.20,
    "fund_flow": 0.15,
    "risk": 0.20,
    "sentiment": 0.10,
    "news": 0.10,
}


def build_decision_context(
    quote: Quote,
    technical: TechnicalAnalysis,
    analysts: list[AnalystReport],
    web: WebSearchResult | None,
    discussion: TeamDiscussion | None = None,
    position: UserPosition | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "quote": {
            "symbol": quote.symbol,
            "name": quote.name,
            "price": quote.price,
            "change_pct": quote.change_pct,
            "turnover_pct": quote.turnover_pct,
            "pe": quote.pe,
            "pb": quote.pb,
        },
        "technical": {
            "score": technical.score,
            "rating": technical.rating,
            "trend": technical.trend,
            "levels": technical.levels.model_dump(),
        },
        "analysts": [analyst.model_dump() for analyst in analysts],
        "data_gaps": sorted(
            {
                item
                for analyst in analysts
                for item in analyst.missing
            }
        ),
    }
    if position is not None:
        context["user_position"] = position.snapshot(quote.price)
    if discussion is not None and discussion.turns:
        context["discussion"] = {
            "summary": discussion.summary,
            "turns": [turn.model_dump() for turn in discussion.turns],
        }
    if web is not None and web.success and web.pages:
        context["public_web_info"] = [
            {
                "title": page.title,
                "site": page.site,
                "date": page.date,
                "summary": page.summary[:300],
            }
            for page in web.pages
        ]
    return context


def _rule_position_advice(
    rating: str,
    position: UserPosition | None,
    price: float | None,
) -> tuple[str | None, str]:
    """规则兜底下的持仓建议：至少保证成本与浮盈亏被用上。"""
    if position is None:
        return None, ""

    pnl_pct: float | None = None
    if position.has_cost and price is not None:
        pnl_pct = (price - position.cost_price) / position.cost_price * 100
        detail = f"成本 {position.cost_price:.2f}，现价 {price:.2f}，浮动 {pnl_pct:+.2f}%"
        if position.quantity is not None:
            amount = (price - position.cost_price) * position.quantity
            detail += f"（约 {amount:+.0f} 元）"
    else:
        detail = "未填写完整成本/数量"

    if rating == "买入":
        action = "加仓" if pnl_pct is not None and pnl_pct < 0 else "建仓"
        advice = f"{detail}；评级偏多，可分批{action}，避免一次性追高。"
    elif rating == "持有":
        action = "持有" if position.has_cost else "观望"
        advice = f"{detail}；评级中性，建议持有观察，跌破支撑再考虑减仓。"
    else:
        action = "清仓" if pnl_pct is not None and pnl_pct <= -8 else "减仓"
        advice = f"{detail}；评级偏空，建议反弹时{action}，严格执行止损。"
    return action, advice


def _rule_decision(
    technical: TechnicalAnalysis,
    analysts: list[AnalystReport],
    user_position: UserPosition | None = None,
    price: float | None = None,
) -> FinalDecision:
    weighted = 0.0
    total_weight = 0.0
    for analyst in analysts:
        weight = _WEIGHTS.get(analyst.key, 0.1)
        weighted += analyst.score * weight
        total_weight += weight
    average = weighted / total_weight if total_weight else 50.0

    if average >= 65:
        rating = "买入"
        operation = "等待回踩支撑后分批建仓，避免追高；跌破止损位离场。"
        holding = "5–10 个交易日"
        position = "轻仓（不超过 3 成）"
    elif average >= 45:
        rating = "持有"
        operation = "已有仓位可持有观察；未持仓等待更明确的多维共振信号。"
        holding = "10–20 个交易日"
        position = "中等仓位（不超过 5 成）"
    else:
        rating = "卖出"
        operation = "控制仓位，反弹减仓；跌破关键支撑应果断离场。"
        holding = "1–5 个交易日"
        position = "空仓或极轻仓"

    sorted_analysts = sorted(analysts, key=lambda item: item.score, reverse=True)
    key_reasons = [
        f"{item.name}：{item.summary}" for item in sorted_analysts[:3] if item.summary
    ]
    risks: list[str] = []
    for item in analysts:
        for risk in item.risks:
            if risk not in risks:
                risks.append(risk)
    risks = risks[:5]
    consensus = [f"{item.name} 偏乐观" for item in analysts if item.score >= 65]
    dissent = [f"{item.name} 偏谨慎" for item in analysts if item.score < 45]
    confidence = max(30, min(90, round(50 + abs(average - 50) * 1.2)))
    position_action, position_advice = _rule_position_advice(
        rating, user_position, price
    )

    return FinalDecision(
        rating=rating,
        confidence=confidence,
        summary=(
            f"六维加权评分 {average:.1f}，给出「{rating}」。"
            f"{'数据完整度一般，' if any(item.missing for item in analysts) else ''}"
            "价位由代码计算，执行时请结合自身风险承受能力。"
        ),
        operation_advice=operation,
        holding_period=holding,
        position_size=position,
        key_reasons=key_reasons,
        risks=risks,
        risk_warning="；".join(risks[:2]) or "注意市场系统性风险与数据缺口。",
        consensus=consensus,
        dissent=dissent,
        levels=technical.levels,
        decision_source="rule_fallback",
        position_action=position_action,
        position_advice=position_advice,
    )


async def build_decision(
    llm_client: LLMClient,
    quote: Quote,
    technical: TechnicalAnalysis,
    analysts: list[AnalystReport],
    web: WebSearchResult | None,
    discussion: TeamDiscussion | None = None,
    position: UserPosition | None = None,
) -> FinalDecision:
    context = build_decision_context(quote, technical, analysts, web, discussion, position)
    try:
        data = await llm_client.generate_json(SYSTEM_PROMPT, build_user_prompt(context))
        draft = DecisionDraft.model_validate(data)
        return FinalDecision(
            **draft.model_dump(),
            levels=technical.levels,
            decision_source="llm",
        )
    except (LLMError, ValueError) as exc:
        logger.warning("首席策略官 LLM 决策失败，使用规则兜底: %s", exc)
        return _rule_decision(technical, analysts, position, quote.price)
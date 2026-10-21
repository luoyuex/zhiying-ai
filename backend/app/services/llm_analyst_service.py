"""六位分析师的 LLM 版：并发调用，逐位失败回退规则稿。"""

import asyncio
from collections.abc import Awaitable, Callable

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.analyst_prompts import build_analyst_context, build_user_prompt, system_prompt_for
from app.llm.client import LLMClient
from app.providers.models import KlineBar, Quote
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.analyst import AnalystDraft, AnalystReport
from app.schemas.company import FinancialData, FundFlowData, SentimentData
from app.schemas.search import WebSearchResult

logger = get_logger(__name__)

_RATING_ALIASES = {
    "乐观": "乐观",
    "看多": "乐观",
    "偏多": "乐观",
    "买入": "乐观",
    "增持": "乐观",
    "中性": "中性",
    "持有": "中性",
    "观望": "中性",
    "谨慎": "谨慎",
    "偏空": "谨慎",
    "看空": "谨慎",
    "卖出": "谨慎",
    "减持": "谨慎",
    "低风险": "低风险",
    "中等风险": "中等风险",
    "中风险": "中等风险",
    "高风险": "高风险",
}


def _default_rating(key: str, score: int) -> str:
    if key == "risk":
        if score >= 70:
            return "低风险"
        return "中等风险" if score >= 45 else "高风险"
    if score >= 65:
        return "乐观"
    return "中性" if score >= 45 else "谨慎"


def normalize_rating(key: str, rating: str, score: int) -> str:
    """模型偶尔给出近义词或空值，统一映射；仍不认识就按分数推导。"""
    text = (rating or "").strip()
    mapped = _RATING_ALIASES.get(text)
    if mapped is None:
        return _default_rating(key, score)
    if key == "risk" and mapped in {"乐观", "中性", "谨慎"}:
        return _default_rating(key, score)
    if key != "risk" and mapped in {"低风险", "中等风险", "高风险"}:
        return _default_rating(key, score)
    return mapped


def _merge_draft(rule: AnalystReport, draft: AnalystDraft) -> AnalystReport:
    score = draft.score if draft.score is not None else rule.score
    return rule.model_copy(
        update={
            "score": score,
            "rating": normalize_rating(rule.key, draft.rating, score),
            "summary": draft.summary or rule.summary,
            "points": draft.points or rule.points,
            "risks": draft.risks or rule.risks,
            "engine": "llm",
        }
    )


async def build_llm_analysts(
    llm_client: LLMClient,
    quote: Quote,
    technical: TechnicalAnalysis,
    bars: list[KlineBar],
    rule_analysts: list[AnalystReport],
    *,
    financial: FinancialData | None = None,
    fund_flow: FundFlowData | None = None,
    sentiment: SentimentData | None = None,
    web: WebSearchResult | None = None,
    on_done: Callable[[AnalystReport], Awaitable[None]] | None = None,
) -> list[AnalystReport]:
    """六位分析师并发调用 LLM；单点失败保留规则稿，不影响整份报告。"""
    semaphore = asyncio.Semaphore(max(1, settings.llm_analyst_concurrency))

    async def run_one(rule: AnalystReport) -> AnalystReport:
        async with semaphore:
            try:
                context = build_analyst_context(
                    rule.key,
                    rule,
                    quote,
                    technical,
                    bars,
                    financial,
                    fund_flow,
                    sentiment,
                    web,
                )
                async with asyncio.timeout(settings.llm_analyst_timeout_seconds):
                    data = await llm_client.generate_json(
                        system_prompt_for(rule.key),
                        build_user_prompt(context),
                    )
                report = _merge_draft(rule, AnalystDraft.model_validate(data))
            except Exception as exc:  # noqa: BLE001 - 单点失败不能拖垮整份报告
                logger.exception("分析师 %s LLM 失败，使用规则稿: %s", rule.key, exc)
                report = rule
        if on_done is not None:
            await on_done(report)
        return report

    return list(await asyncio.gather(*(run_one(rule) for rule in rule_analysts)))

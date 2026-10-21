"""AI 多分析师报告：六维分析、首席决策、6 小时缓存与每日额度。"""

import hashlib
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.client import LLMClient, LLMNotConfiguredError, is_llm_configured
from app.llm.prompts import PROMPT_VERSION
from app.providers.models import KlineBar, Quote
from app.schemas.ai import AIAnalysisPayload, AIAnalysisResponse
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.analyst import FinalDecision
from app.schemas.company import FinancialData, FundFlowData, SentimentData
from app.schemas.search import WebSearchResult
from app.services.analyst_service import build_analysts
from app.services.decision_service import build_decision
from app.services.web_search_service import sources_for_response

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
DISCLAIMER = (
    "本报告由六维分析师与首席策略官基于给定数据生成，仅供研究参考，不构成投资建议；"
    "价位由系统代码计算。"
)


class QuotaExceededError(Exception):
    def __init__(self, limit: int, reset_seconds: int) -> None:
        super().__init__("今日 AI 分析额度已用完")
        self.limit = limit
        self.reset_seconds = reset_seconds


class QuotaServiceError(Exception):
    pass


def _today() -> str:
    return datetime.now(TZ_SHANGHAI).strftime("%Y-%m-%d")


def _seconds_to_midnight() -> int:
    now = datetime.now(TZ_SHANGHAI)
    tomorrow = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=TZ_SHANGHAI)
    return max(1, int((tomorrow - now).total_seconds()))


def quota_key(user_id: object) -> str:
    return f"ai:quota:{user_id}:{_today()}"


async def read_quota_used(redis: Redis, user_id: object, *, strict: bool = False) -> int:
    try:
        raw = await redis.get(quota_key(user_id))
        return int(raw or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 AI 额度失败: %s", exc)
        if strict:
            raise QuotaServiceError("AI 额度服务暂不可用") from exc
        return 0


def _cache_key(quote: Quote) -> str:
    trade_date = quote.fetched_at.astimezone(TZ_SHANGHAI).strftime("%Y-%m-%d")
    model_digest = hashlib.sha1(settings.llm_model.encode("utf-8")).hexdigest()[:8]
    return f"ai:report:{quote.symbol}:{trade_date}:{PROMPT_VERSION}:{model_digest}"


async def cache_ai_report(redis: Redis, quote: Quote, report: AIAnalysisResponse) -> None:
    try:
        await redis.set(
            _cache_key(quote),
            report.model_dump_json(),
            ex=settings.llm_cache_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("更新 AI 报告缓存失败: %s", exc)


def _headline_from_decision(
    decision: FinalDecision,
    technical: TechnicalAnalysis,
) -> AIAnalysisPayload:
    rating_map = {"买入": "看多", "持有": "中性", "卖出": "看空"}
    trend_map = {
        "上升趋势": "上升",
        "偏强整理": "上升",
        "下降趋势": "下降",
        "偏弱整理": "下降",
        "震荡整理": "震荡",
    }
    return AIAnalysisPayload(
        rating=rating_map[decision.rating],
        confidence=decision.confidence,
        trend=trend_map.get(technical.trend, "震荡"),
        summary=decision.summary,
        key_points=decision.key_reasons[:5],
        risks=decision.risks[:5],
        watch=decision.operation_advice[:300],
    )


async def get_cached_ai_report(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    quote: Quote,
) -> AIAnalysisResponse | None:
    """在搜索/LLM 之前检查 6h 缓存，避免重复消耗元宝搜索和 LLM。"""
    try:
        raw = await redis.get(_cache_key(quote))
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 AI 缓存失败: %s", exc)
        return None
    if not raw:
        return None
    try:
        report = AIAnalysisResponse.model_validate_json(raw)
    except ValidationError:
        logger.warning("AI 缓存内容损坏，忽略")
        return None
    quota_used = await read_quota_used(redis, user_id, strict=False)
    return report.model_copy(
        update={
            "cached": True,
            "quota_used": quota_used,
            "quota_limit": daily_quota,
        }
    )


async def generate_ai_analysis(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    quote: Quote,
    technical: TechnicalAnalysis,
    bars: list[KlineBar],
    *,
    financial: FinancialData | None = None,
    fund_flow: FundFlowData | None = None,
    sentiment: SentimentData | None = None,
    web: WebSearchResult | None = None,
    llm_client: LLMClient | None = None,
) -> AIAnalysisResponse:
    if llm_client is None:
        if not is_llm_configured():
            raise LLMNotConfiguredError("尚未配置 LLM")
        llm_client = LLMClient()

    quota_used = await read_quota_used(redis, user_id, strict=True)
    cache_key = _cache_key(quote)

    try:
        cached_raw = await redis.get(cache_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 AI 缓存失败: %s", exc)
        cached_raw = None
    if cached_raw:
        try:
            cached = AIAnalysisResponse.model_validate_json(cached_raw)
            return cached.model_copy(
                update={
                    "cached": True,
                    "quota_used": quota_used,
                    "quota_limit": daily_quota,
                }
            )
        except ValidationError:
            logger.warning("AI 缓存内容损坏，重新生成")

    if quota_used >= daily_quota:
        raise QuotaExceededError(daily_quota, _seconds_to_midnight())

    analysts = build_analysts(
        quote,
        technical,
        financial,
        fund_flow,
        sentiment,
        web,
        bars,
    )
    decision = await build_decision(llm_client, quote, technical, analysts, web)
    headline = _headline_from_decision(decision, technical)

    now = datetime.now(TZ_SHANGHAI)
    web_used = bool(web is not None and web.success and web.pages)
    sources = {technical.source}
    if financial is not None:
        sources.add(financial.source)
    if fund_flow is not None:
        sources.add(fund_flow.source)
    if sentiment is not None:
        sources.add(sentiment.source)

    report = AIAnalysisResponse(
        symbol=quote.symbol,
        name=quote.name,
        price=quote.price,
        change_pct=quote.change_pct,
        model=settings.llm_model,
        prompt_version=PROMPT_VERSION,
        generated_at=now,
        data_as_of=quote.fetched_at,
        data_source=" / ".join(sorted(sources)),
        cached=False,
        quota_used=quota_used + 1,
        quota_limit=daily_quota,
        analysis=headline,
        analysts=analysts,
        decision=decision,
        web_search_used=web_used,
        web_sources=sources_for_response(web) if web_used else [],
        disclaimer=DISCLAIMER,
    )

    try:
        await redis.set(cache_key, report.model_dump_json(), ex=settings.llm_cache_seconds)
        new_used = await redis.incr(quota_key(user_id))
        if new_used == 1:
            await redis.expire(quota_key(user_id), _seconds_to_midnight())
        report = report.model_copy(update={"quota_used": new_used})
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入 AI 缓存/额度失败: %s", exc)

    return report

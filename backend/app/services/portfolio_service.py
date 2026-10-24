"""组合 AI 诊断：汇总自选股与持仓，一次 LLM 调用给出调仓建议。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.core.telemetry import bind_context
from app.llm.client import LLMClient, LLMNotConfiguredError, is_llm_configured
from app.llm.portfolio_prompts import SYSTEM_PROMPT, build_portfolio_prompt
from app.schemas.portfolio import (
    PortfolioDiagnosisDraft,
    PortfolioDiagnosisResponse,
    PortfolioPositionAdvice,
)
from app.schemas.watchlist import WatchlistEntry
from app.services.ai_analysis_service import (
    QuotaExceededError,
    quota_key,
    read_quota_used,
    seconds_to_midnight,
)
from app.services.market_service import MarketDataService
from app.services.report_history_service import save_portfolio_diagnosis
from app.services.watchlist_service import list_watchlist

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


class PortfolioEmptyError(Exception):
    pass


def _pnl(entry: WatchlistEntry) -> tuple[float | None, float | None]:
    if entry.cost_price is None or entry.price is None or entry.cost_price <= 0:
        return None, None
    pct = (entry.price - entry.cost_price) / entry.cost_price * 100
    amount = None
    if entry.quantity is not None:
        amount = (entry.price - entry.cost_price) * entry.quantity
    return round(pct, 2), (round(amount, 2) if amount is not None else None)


def build_portfolio_context(entries: list[WatchlistEntry]) -> dict:
    positions: list[dict] = []
    for entry in entries:
        pnl_pct, pnl_amount = _pnl(entry)
        item: dict = {
            "symbol": entry.symbol,
            "name": entry.name,
            "price": entry.price,
            "change_pct": entry.change_pct,
        }
        if entry.cost_price is not None:
            item["cost_price"] = entry.cost_price
        if entry.quantity is not None:
            item["quantity"] = entry.quantity
        if pnl_pct is not None:
            item["pnl_pct"] = pnl_pct
        if pnl_amount is not None:
            item["pnl_amount"] = pnl_amount
        if entry.price is not None and entry.quantity is not None:
            item["market_value"] = round(entry.price * entry.quantity, 2)
        if entry.note:
            item["note"] = entry.note
        if entry.latest is not None:
            item["latest_analysis"] = {
                "rating": entry.latest.rating,
                "confidence": entry.latest.confidence,
                "position_action": entry.latest.position_action,
                "summary": entry.latest.summary,
            }
        positions.append(item)
    return {"positions": positions}


def _merge_positions(
    entries: list[WatchlistEntry],
    draft: PortfolioDiagnosisDraft,
) -> list[PortfolioPositionAdvice]:
    """以自选列表为准：补齐名称，忽略模型编造的股票，缺失给观望。"""
    by_symbol = {item.symbol: item for item in draft.positions}
    merged: list[PortfolioPositionAdvice] = []
    for entry in entries:
        advice = by_symbol.get(entry.symbol)
        if advice is None:
            merged.append(
                PortfolioPositionAdvice(
                    symbol=entry.symbol,
                    name=entry.name,
                    action="观望",
                    reason="AI 未给出明确建议",
                )
            )
        else:
            merged.append(advice.model_copy(update={"name": entry.name}))
    return merged


async def diagnose_portfolio(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    market: MarketDataService,
    *,
    llm_client: LLMClient | None = None,
) -> PortfolioDiagnosisResponse:
    if llm_client is None:
        if not is_llm_configured():
            raise LLMNotConfiguredError("尚未配置 LLM")
        llm_client = LLMClient()

    entries = await list_watchlist(user_id, market)
    if not entries:
        raise PortfolioEmptyError

    quota_used = await read_quota_used(redis, user_id, strict=True)
    if quota_used >= daily_quota:
        raise QuotaExceededError(daily_quota, seconds_to_midnight())

    with bind_context(user_id=user_id, task="portfolio"):
        data = await llm_client.generate_json(
            SYSTEM_PROMPT,
            build_portfolio_prompt(build_portfolio_context(entries)),
        )
    draft = PortfolioDiagnosisDraft.model_validate(data)

    new_used = quota_used + 1
    try:
        new_used = await redis.incr(quota_key(user_id))
        if new_used == 1:
            await redis.expire(quota_key(user_id), seconds_to_midnight())
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入组合诊断额度失败: %s", exc)

    result = PortfolioDiagnosisResponse(
        health_score=draft.health_score,
        summary=draft.summary,
        risk_notes=draft.risk_notes,
        allocation_advice=draft.allocation_advice,
        positions=_merge_positions(entries, draft),
        generated_at=datetime.now(TZ_SHANGHAI),
        model=settings.llm_model,
        quota_used=new_used,
        quota_limit=daily_quota,
    )
    try:
        record_id = await save_portfolio_diagnosis(user_id, result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("保存组合诊断失败: %s", exc)
    else:
        result = result.model_copy(update={"id": record_id})
    return result

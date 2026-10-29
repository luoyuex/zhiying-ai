"""自选股接口。"""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import ValidationError
from redis.asyncio import Redis

from app.core import errors
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.redis import get_redis
from app.llm.client import (
    LLMNotConfiguredError,
    LLMRateLimitedError,
    LLMRequestError,
    LLMResponseError,
)
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.portfolio import (
    PortfolioDiagnosisDetail,
    PortfolioDiagnosisResponse,
    PortfolioDiagnosisSummary,
)
from app.schemas.watchlist import (
    PositionChangeEntry,
    PriceAlertCreateRequest,
    PriceAlertView,
    WatchlistAddRequest,
    WatchlistAddResponse,
    WatchlistBatchRequest,
    WatchlistBatchResult,
    WatchlistEntry,
    WatchlistOrderRequest,
    WatchlistOrderResponse,
    WatchlistStatus,
    WatchlistUpdateRequest,
)
from app.services.ai_analysis_service import QuotaExceededError, QuotaServiceError
from app.services.market_service import MarketDataService
from app.services.portfolio_service import PortfolioEmptyError, diagnose_portfolio
from app.services.price_alert_service import (
    MAX_ACTIVE_ALERTS_PER_USER,
    PriceAlertLimitError,
    PriceAlertReportError,
    cancel_alert,
    create_alert,
    list_alerts,
)
from app.services.report_history_service import (
    get_latest_portfolio_diagnosis,
    get_portfolio_diagnosis,
    list_portfolio_diagnoses,
)
from app.services.watchlist_service import (
    MAX_WATCHLIST,
    WatchlistLimitError,
    add_watchlist,
    batch_analyze,
    is_watchlisted,
    list_position_history,
    list_watchlist,
    remove_watchlist,
    reorder_watchlist,
    update_watchlist,
)

router = APIRouter(prefix="/watchlist", tags=["自选股"])


def get_market_service(redis: Redis = Depends(get_redis)) -> MarketDataService:
    return MarketDataService(redis)


@router.get("", response_model=list[WatchlistEntry], summary="自选股列表")
async def get_watchlist(
    user: User = Depends(get_current_user),
    market: MarketDataService = Depends(get_market_service),
) -> list[WatchlistEntry]:
    return await list_watchlist(user.id, market)


@router.post("", response_model=WatchlistAddResponse, summary="加入自选")
async def add(
    payload: WatchlistAddRequest,
    user: User = Depends(get_current_user),
) -> WatchlistAddResponse:
    try:
        symbol, added = await add_watchlist(
            user.id,
            payload.symbol,
            note=payload.note,
            cost_price=payload.cost_price,
            quantity=payload.quantity,
        )
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    except WatchlistLimitError as exc:
        raise errors.watchlist_full(MAX_WATCHLIST) from exc
    return WatchlistAddResponse(symbol=symbol, added=added)


@router.patch("/order", response_model=WatchlistOrderResponse, summary="调整自选顺序")
async def reorder(
    payload: WatchlistOrderRequest,
    user: User = Depends(get_current_user),
) -> WatchlistOrderResponse:
    # 必须声明在 /{symbol} 之前，否则 "order" 会被当成股票代码
    symbols = await reorder_watchlist(user.id, payload.symbols)
    return WatchlistOrderResponse(symbols=symbols)


@router.patch("/{symbol}", response_model=WatchlistStatus, summary="更新自选信息")
async def update(
    symbol: str,
    payload: WatchlistUpdateRequest,
    user: User = Depends(get_current_user),
) -> WatchlistStatus:
    changes = payload.model_dump(exclude_unset=True)
    if "note" in changes:
        changes["note"] = str(changes["note"] or "").strip()[:120]
    try:
        code = parse_symbol(symbol).code
        updated = await update_watchlist(user.id, code, changes)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    if not updated:
        raise errors.not_found("该股票不在自选列表中")
    return WatchlistStatus(symbol=code, in_watchlist=True)


@router.post(
    "/batch-analysis",
    response_model=list[WatchlistBatchResult],
    summary="批量分析自选股",
)
async def batch(
    payload: WatchlistBatchRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> list[WatchlistBatchResult]:
    return await batch_analyze(
        user.id,
        settings.effective_daily_quota(user.daily_analysis_quota),
        payload.symbols,
        redis,
        force=payload.force,
    )


@router.post(
    "/portfolio-analysis",
    response_model=PortfolioDiagnosisResponse,
    summary="AI 组合诊断",
)
async def portfolio_diagnosis(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    market: MarketDataService = Depends(get_market_service),
) -> PortfolioDiagnosisResponse:
    try:
        return await diagnose_portfolio(
            redis,
            user.id,
            settings.effective_daily_quota(user.daily_analysis_quota),
            market,
        )
    except PortfolioEmptyError as exc:
        raise errors.portfolio_empty() from exc
    except QuotaExceededError as exc:
        raise errors.analysis_quota_exceeded(exc.limit, exc.reset_seconds) from exc
    except QuotaServiceError as exc:
        raise errors.ai_service_unavailable(str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise errors.llm_not_configured() from exc
    except LLMRateLimitedError as exc:
        raise errors.llm_busy() from exc
    except LLMResponseError as exc:
        raise errors.llm_invalid_response() from exc
    except LLMRequestError as exc:
        raise errors.llm_error() from exc
    except ValidationError as exc:
        raise errors.llm_invalid_response() from exc


@router.get(
    "/portfolio-analysis/history",
    response_model=list[PortfolioDiagnosisSummary],
    summary="组合诊断历史",
)
async def portfolio_history(
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
) -> list[PortfolioDiagnosisSummary]:
    return await list_portfolio_diagnoses(user.id, limit=limit)


@router.get(
    "/portfolio-analysis/latest",
    response_model=PortfolioDiagnosisDetail | None,
    summary="最近一次组合诊断",
)
async def portfolio_latest(
    user: User = Depends(get_current_user),
) -> PortfolioDiagnosisDetail | None:
    return await get_latest_portfolio_diagnosis(user.id)


@router.get(
    "/portfolio-analysis/history/{record_id}",
    response_model=PortfolioDiagnosisDetail,
    summary="组合诊断详情",
)
async def portfolio_history_detail(
    record_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> PortfolioDiagnosisDetail:
    detail = await get_portfolio_diagnosis(user.id, record_id)
    if detail is None:
        raise errors.not_found("组合诊断记录不存在")
    return detail


@router.get("/alerts", response_model=list[PriceAlertView], summary="价位提醒列表")
async def alerts_list(
    user: User = Depends(get_current_user),
) -> list[PriceAlertView]:
    return await list_alerts(user.id)


@router.post(
    "/{symbol}/alerts",
    response_model=PriceAlertView,
    summary="创建价位提醒",
)
async def create_price_alert(
    symbol: str,
    payload: PriceAlertCreateRequest,
    user: User = Depends(get_current_user),
) -> PriceAlertView:
    try:
        return await create_alert(
            user.id,
            symbol,
            direction=payload.direction,
            target_price=payload.target_price,
            kind=payload.kind,
            report_id=payload.report_id,
        )
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    except PriceAlertReportError as exc:
        raise errors.validation(str(exc)) from exc
    except PriceAlertLimitError as exc:
        raise errors.price_alert_limit(MAX_ACTIVE_ALERTS_PER_USER) from exc


@router.delete("/alerts/{alert_id}", status_code=204, summary="取消价位提醒")
async def cancel_price_alert(
    alert_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> Response:
    cancelled = await cancel_alert(user.id, alert_id)
    if not cancelled:
        raise errors.not_found("提醒不存在或已结束")
    return Response(status_code=204)


@router.get(
    "/{symbol}/position-history",
    response_model=list[PositionChangeEntry],
    summary="调仓记录",
)
async def position_history(
    symbol: str,
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> list[PositionChangeEntry]:
    try:
        return await list_position_history(user.id, symbol, limit=limit)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc


@router.get("/{symbol}", response_model=WatchlistStatus, summary="是否已自选")
async def status(symbol: str, user: User = Depends(get_current_user)) -> WatchlistStatus:
    try:
        code = parse_symbol(symbol).code
        exists = await is_watchlisted(user.id, code)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    return WatchlistStatus(symbol=code, in_watchlist=exists)


@router.delete("/{symbol}", status_code=204, summary="移出自选")
async def remove(symbol: str, user: User = Depends(get_current_user)) -> Response:
    try:
        await remove_watchlist(user.id, symbol)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    return Response(status_code=204)

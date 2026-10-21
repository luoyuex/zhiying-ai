"""自选股接口。"""

from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis

from app.core import errors
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.redis import get_redis
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.watchlist import (
    WatchlistAddRequest,
    WatchlistAddResponse,
    WatchlistBatchRequest,
    WatchlistBatchResult,
    WatchlistEntry,
    WatchlistStatus,
    WatchlistUpdateRequest,
)
from app.services.market_service import MarketDataService
from app.services.watchlist_service import (
    MAX_WATCHLIST,
    WatchlistLimitError,
    add_watchlist,
    batch_analyze,
    is_watchlisted,
    list_watchlist,
    remove_watchlist,
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

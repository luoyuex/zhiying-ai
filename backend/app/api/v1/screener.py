"""选股接口：策略列表与主力选股。"""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core import errors
from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.redis import get_redis
from app.providers.base import DataNotFound, ProviderSchemaDrift, ProviderUnavailable
from app.schemas.screener import (
    LowPriceBullRequest,
    LowPriceBullResponse,
    MainForceScreenRequest,
    MainForceScreenResponse,
    ScreenerStrategy,
)
from app.services.screener_service import (
    STRATEGIES,
    screen_low_price_bull,
    screen_main_force,
)

router = APIRouter(prefix="/screener", tags=["选股"])


@router.get("/strategies", response_model=list[ScreenerStrategy], summary="选股策略列表")
async def list_strategies(_: User = Depends(get_current_user)) -> list[ScreenerStrategy]:
    return STRATEGIES


@router.post(
    "/main-force",
    response_model=MainForceScreenResponse,
    summary="主力选股（超大单净流入排名）",
)
async def main_force(
    payload: MainForceScreenRequest,
    _: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> MainForceScreenResponse:
    try:
        return await screen_main_force(redis, payload)
    except (ProviderUnavailable, DataNotFound, ProviderSchemaDrift) as exc:
        raise errors.market_unavailable() from exc


@router.post(
    "/low-price-bull",
    response_model=LowPriceBullResponse,
    summary="低价擒牛（低价 + 高净利增长）",
)
async def low_price_bull(
    payload: LowPriceBullRequest,
    _: User = Depends(get_current_user),
) -> LowPriceBullResponse:
    try:
        return await screen_low_price_bull(payload)
    except (ProviderUnavailable, DataNotFound, ProviderSchemaDrift) as exc:
        raise errors.market_unavailable() from exc

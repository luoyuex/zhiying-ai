"""个股行情接口。"""

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.core import errors
from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.redis import get_redis
from app.llm.client import LLMNotConfiguredError, is_llm_configured
from app.providers.base import DataNotFound, MarketUnavailable
from app.providers.models import Adjust, KlinePeriod, KlineSeries, Quote
from app.providers.symbols import InvalidSymbolError
from app.schemas.ai import AIJobState
from app.schemas.analysis import TechnicalAnalysis
from app.services.ai_job_service import start_ai_job
from app.services.market_service import MarketDataService
from app.services.technical_analysis import InsufficientDataError, analyze_technicals

logger = get_logger(__name__)

router = APIRouter(prefix="/stocks", tags=["行情"])


def get_market_service(redis: Redis = Depends(get_redis)) -> MarketDataService:
    return MarketDataService(redis)


async def _technical_snapshot(symbol: str, service: MarketDataService):
    quote = await service.get_quote(symbol)
    kline = await service.get_kline(
        symbol,
        period=KlinePeriod.DAY,
        adjust=Adjust.QFQ,
        limit=90,
    )
    technical = analyze_technicals(quote, kline.bars, kline.source)
    return quote, kline, technical


@router.get("/{symbol}/quote", response_model=Quote, summary="实时报价")
async def get_quote(
    symbol: str,
    _: User = Depends(get_current_user),
    service: MarketDataService = Depends(get_market_service),
) -> Quote:
    try:
        return await service.get_quote(symbol)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    except DataNotFound as exc:
        raise errors.stock_not_found(symbol) from exc
    except MarketUnavailable as exc:
        logger.warning("报价全源失败 %s: %s", symbol, exc)
        raise errors.market_unavailable() from exc


@router.get("/{symbol}/kline", response_model=KlineSeries, summary="K 线")
async def get_kline(
    symbol: str,
    period: KlinePeriod = Query(KlinePeriod.DAY, description="K 线周期"),
    adjust: Adjust = Query(Adjust.QFQ, description="复权方式"),
    limit: int = Query(250, ge=1, le=800, description="返回条数"),
    _: User = Depends(get_current_user),
    service: MarketDataService = Depends(get_market_service),
) -> KlineSeries:
    try:
        return await service.get_kline(
            symbol, period=period, adjust=adjust, limit=limit
        )
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    except DataNotFound as exc:
        raise errors.stock_not_found(symbol) from exc
    except MarketUnavailable as exc:
        logger.warning("K 线全源失败 %s: %s", symbol, exc)
        raise errors.market_unavailable() from exc


@router.get("/{symbol}/analysis", response_model=TechnicalAnalysis, summary="技术面诊断")
async def get_analysis(
    symbol: str,
    _: User = Depends(get_current_user),
    service: MarketDataService = Depends(get_market_service),
) -> TechnicalAnalysis:
    try:
        _, _, technical = await _technical_snapshot(symbol, service)
        return technical
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    except DataNotFound as exc:
        raise errors.stock_not_found(symbol) from exc
    except MarketUnavailable as exc:
        logger.warning("技术诊断全源失败 %s: %s", symbol, exc)
        raise errors.market_unavailable() from exc
    except InsufficientDataError as exc:
        raise errors.analysis_unavailable(str(exc)) from exc


@router.post(
    "/{symbol}/ai-analysis",
    response_model=AIJobState,
    status_code=202,
    summary="创建 AI 分析任务",
)
async def create_ai_analysis(
    symbol: str,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> AIJobState:
    if not is_llm_configured():
        raise errors.llm_not_configured()

    try:
        return await start_ai_job(
            redis,
            user.id,
            user.daily_analysis_quota,
            symbol,
        )
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise errors.llm_not_configured() from exc

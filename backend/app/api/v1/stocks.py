"""个股行情接口。"""

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.core import errors
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.redis import get_redis
from app.llm.client import LLMNotConfiguredError, is_llm_configured
from app.providers.base import DataNotFound, MarketUnavailable
from app.providers.fundflow import get_fund_flow
from app.providers.models import Adjust, KlinePeriod, KlineSeries, Quote
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.ai import AIJobState
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.company import FundFlowData
from app.schemas.news import CompanyNewsData
from app.schemas.search import WebSearchResult
from app.schemas.stock import StockSearchItem
from app.services.ai_analysis_service import QuotaExceededError, QuotaServiceError
from app.services.ai_job_service import AIWorkerUnavailableError, start_ai_job
from app.services.company_news_service import get_company_news
from app.services.market_service import MarketDataService
from app.services.stock_directory_service import search_stocks as search_stock_directory
from app.services.technical_analysis import InsufficientDataError, analyze_technicals
from app.services.web_search_service import search_symbol_web

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


@router.get("/search", response_model=list[StockSearchItem], summary="股票搜索")
async def search_stocks(
    q: str = Query(..., min_length=1, max_length=20, description="代码 / 名称 / 全拼 / 首字母"),
    limit: int = Query(10, ge=1, le=20, description="返回条数"),
    _: User = Depends(get_current_user),
) -> list[StockSearchItem]:
    return await search_stock_directory(q, limit=limit)


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


@router.get("/{symbol}/fund-flow", response_model=FundFlowData, summary="个股资金流")
async def get_stock_fund_flow(
    symbol: str,
    _: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> FundFlowData:
    try:
        parsed = parse_symbol(symbol)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc

    data = await get_fund_flow(redis, parsed.code)
    if data is None or not data.days:
        raise errors.market_unavailable()
    return data


@router.get("/{symbol}/news", response_model=CompanyNewsData, summary="个股公告与新闻")
async def get_stock_news(
    symbol: str,
    limit: int = Query(20, ge=1, le=50, description="每类返回条数"),
    _: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    service: MarketDataService = Depends(get_market_service),
) -> CompanyNewsData:
    try:
        parsed = parse_symbol(symbol)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc

    name = ""
    try:
        name = (await service.get_quote(parsed.code)).name
    except Exception:  # noqa: BLE001
        # 名称只用于新闻检索关键词，取不到时退回代码，不阻塞资讯
        pass

    try:
        return await get_company_news(redis, parsed.code, name=name, limit=limit)
    except MarketUnavailable as exc:
        logger.warning("资讯全源失败 %s: %s", parsed.code, exc)
        raise errors.market_unavailable() from exc


@router.post(
    "/{symbol}/news/ai-search",
    response_model=WebSearchResult,
    summary="按需检索公开资讯（元宝）",
)
async def ai_search_stock_news(
    symbol: str,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    service: MarketDataService = Depends(get_market_service),
) -> WebSearchResult:
    try:
        parsed = parse_symbol(symbol)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc

    cooldown_key = f"web:search:cooldown:{user.id}:{parsed.code}"
    acquired = True
    try:
        acquired = bool(await redis.set(cooldown_key, "1", ex=30, nx=True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("元宝检索冷却检查失败: %s", exc)
    if not acquired:
        raise errors.rate_limited("检索过于频繁，请 30 秒后再试", 30)

    try:
        quote = await service.get_quote(parsed.code)
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    except DataNotFound as exc:
        raise errors.stock_not_found(parsed.code) from exc
    except MarketUnavailable as exc:
        raise errors.market_unavailable() from exc

    return await search_symbol_web(
        redis,
        quote,
        cache_seconds=settings.market_news_ai_cache_seconds,
    )


@router.post(
    "/{symbol}/ai-analysis",
    response_model=AIJobState,
    status_code=202,
    summary="创建 AI 分析任务",
)
async def create_ai_analysis(
    symbol: str,
    force: bool = Query(False, description="跳过 6 小时缓存，重新生成"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> AIJobState:
    if not is_llm_configured():
        raise errors.llm_not_configured()

    try:
        return await start_ai_job(
            redis,
            user.id,
            settings.effective_daily_quota(user.daily_analysis_quota),
            symbol,
            force,
        )
    except InvalidSymbolError as exc:
        raise errors.invalid_symbol(str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise errors.llm_not_configured() from exc
    except QuotaExceededError as exc:
        raise errors.analysis_quota_exceeded(exc.limit, exc.reset_seconds) from exc
    except QuotaServiceError as exc:
        raise errors.ai_service_unavailable(str(exc)) from exc
    except AIWorkerUnavailableError as exc:
        raise errors.ai_service_unavailable(str(exc)) from exc

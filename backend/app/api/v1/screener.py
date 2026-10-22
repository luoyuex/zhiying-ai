"""选股接口：策略列表、主力选股与历史记录。"""

import uuid

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.core import errors
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.redis import get_redis
from app.llm.client import (
    LLMNotConfiguredError,
    LLMRateLimitedError,
    LLMRequestError,
    LLMResponseError,
)
from app.providers.base import DataNotFound, ProviderSchemaDrift, ProviderUnavailable
from app.schemas.screener import (
    LowPriceBullAnalysisRequest,
    LowPriceBullRequest,
    LowPriceBullResponse,
    MainForceAnalysisRequest,
    MainForceAnalysisResponse,
    MainForceRecordDetail,
    MainForceRecordSummary,
    MainForceScreenRequest,
    MainForceScreenResponse,
    ProfitGrowthAnalysisRequest,
    ScreenerJobState,
    ScreenerStrategy,
    ScreenerStrategyId,
    SmallCapAnalysisRequest,
    SmallCapRequest,
    SmallCapResponse,
    ValueStockAnalysisRequest,
)
from app.services.ai_analysis_service import QuotaExceededError, QuotaServiceError
from app.services.ai_job_service import AIWorkerUnavailableError
from app.services.main_force_analysis_service import (
    MainForceEmptyError,
    analyze_main_force,
)
from app.services.screener_history_service import (
    get_screener_record,
    list_screener_records,
    save_screener_record,
)
from app.services.screener_job_service import (
    ScreenerJobForbiddenError,
    ScreenerJobNotFoundError,
    get_active_screener_job,
    get_screener_job,
    start_screener_job,
)
from app.services.screener_service import (
    STRATEGIES,
    screen_low_price_bull,
    screen_main_force,
    screen_small_cap,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/screener", tags=["选股"])


async def _start_strategy_job(
    redis: Redis,
    user: User,
    strategy: ScreenerStrategyId,
    payload: MainForceAnalysisRequest
    | LowPriceBullAnalysisRequest
    | SmallCapAnalysisRequest
    | ProfitGrowthAnalysisRequest
    | ValueStockAnalysisRequest,
) -> ScreenerJobState:
    try:
        return await start_screener_job(
            redis,
            user.id,
            settings.effective_daily_quota(user.daily_analysis_quota),
            strategy,
            payload,
        )
    except AIWorkerUnavailableError as exc:
        raise errors.ai_service_unavailable(str(exc)) from exc
    except QuotaExceededError as exc:
        raise errors.analysis_quota_exceeded(exc.limit, exc.reset_seconds) from exc
    except QuotaServiceError as exc:
        raise errors.ai_service_unavailable(str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise errors.llm_not_configured() from exc


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
    "/main-force/analysis",
    response_model=MainForceAnalysisResponse,
    summary="主力选股 AI 深度分析（三分析师 + 资深研究员精选）",
)
async def main_force_analysis(
    payload: MainForceAnalysisRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> MainForceAnalysisResponse:
    try:
        response = await analyze_main_force(
            redis,
            user.id,
            settings.effective_daily_quota(user.daily_analysis_quota),
            payload,
        )
    except MainForceEmptyError as exc:
        raise errors.analysis_unavailable(str(exc)) from exc
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

    try:
        record_id = await save_screener_record(
            user.id,
            "main_force",
            payload.model_dump(mode="json"),
            response,
        )
    except Exception as exc:  # noqa: BLE001 - 记录失败不影响本次分析结果
        logger.exception("保存主力选股记录失败: %s", exc)
    else:
        response = response.model_copy(update={"record_id": record_id})
    return response


@router.post(
    "/main-force/jobs",
    response_model=ScreenerJobState,
    summary="发起主力选股 AI 任务",
)
async def create_main_force_job(
    payload: MainForceAnalysisRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState:
    return await _start_strategy_job(redis, user, "main_force", payload)


@router.post(
    "/low-price-bull/jobs",
    response_model=ScreenerJobState,
    summary="发起低价擒牛 AI 任务",
)
async def create_low_price_bull_job(
    payload: LowPriceBullAnalysisRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState:
    return await _start_strategy_job(redis, user, "low_price_bull", payload)


@router.post(
    "/small-cap/jobs",
    response_model=ScreenerJobState,
    summary="发起小市值 AI 任务",
)
async def create_small_cap_job(
    payload: SmallCapAnalysisRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState:
    return await _start_strategy_job(redis, user, "small_cap", payload)


@router.post(
    "/profit-growth/jobs",
    response_model=ScreenerJobState,
    summary="发起净利增长 AI 任务",
)
async def create_profit_growth_job(
    payload: ProfitGrowthAnalysisRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState:
    return await _start_strategy_job(redis, user, "profit_growth", payload)


@router.post(
    "/value-stock/jobs",
    response_model=ScreenerJobState,
    summary="发起低估值 AI 任务",
)
async def create_value_stock_job(
    payload: ValueStockAnalysisRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState:
    return await _start_strategy_job(redis, user, "value_stock", payload)


@router.get(
    "/main-force/jobs/active",
    response_model=ScreenerJobState | None,
    summary="查询主力选股活跃任务",
)
async def get_active_main_force_job(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState | None:
    return await get_active_screener_job(redis, user.id, "main_force")


@router.get(
    "/main-force/jobs/{job_id}",
    response_model=ScreenerJobState,
    summary="查询主力选股任务",
)
async def get_main_force_job(
    job_id: str,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState:
    try:
        return await get_screener_job(redis, user.id, job_id)
    except ScreenerJobNotFoundError as exc:
        raise errors.not_found("选股任务不存在或已过期") from exc
    except ScreenerJobForbiddenError as exc:
        raise errors.forbidden() from exc


@router.get(
    "/jobs/active",
    response_model=ScreenerJobState | None,
    summary="查询选股活跃任务",
)
async def get_active_strategy_job(
    strategy: ScreenerStrategyId = Query(...),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState | None:
    return await get_active_screener_job(redis, user.id, strategy)


@router.get(
    "/jobs/{job_id}",
    response_model=ScreenerJobState,
    summary="查询选股任务",
)
async def get_strategy_job(
    job_id: str,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScreenerJobState:
    try:
        return await get_screener_job(redis, user.id, job_id)
    except ScreenerJobNotFoundError as exc:
        raise errors.not_found("选股任务不存在或已过期") from exc
    except ScreenerJobForbiddenError as exc:
        raise errors.forbidden() from exc


@router.get(
    "/records",
    response_model=list[MainForceRecordSummary],
    summary="选股历史记录",
)
async def list_strategy_records(
    strategy: ScreenerStrategyId = Query("main_force"),
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
) -> list[MainForceRecordSummary]:
    return await list_screener_records(user.id, strategy, limit)


@router.get(
    "/records/{record_id}",
    response_model=MainForceRecordDetail,
    summary="选股记录详情",
)
async def get_strategy_record(
    record_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> MainForceRecordDetail:
    detail = await get_screener_record(user.id, record_id)
    if detail is None:
        raise errors.not_found("选股记录不存在")
    return detail


@router.get(
    "/main-force/records",
    response_model=list[MainForceRecordSummary],
    summary="主力选股历史记录",
)
async def list_main_force_records(
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
) -> list[MainForceRecordSummary]:
    return await list_screener_records(user.id, "main_force", limit)


@router.get(
    "/main-force/records/{record_id}",
    response_model=MainForceRecordDetail,
    summary="主力选股记录详情",
)
async def get_main_force_record(
    record_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> MainForceRecordDetail:
    detail = await get_screener_record(user.id, record_id, "main_force")
    if detail is None:
        raise errors.not_found("选股记录不存在")
    return detail


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


@router.post(
    "/small-cap",
    response_model=SmallCapResponse,
    summary="小市值（小盘 + 营收/净利增长）",
)
async def small_cap(
    payload: SmallCapRequest,
    _: User = Depends(get_current_user),
) -> SmallCapResponse:
    try:
        return await screen_small_cap(payload)
    except (ProviderUnavailable, DataNotFound, ProviderSchemaDrift) as exc:
        raise errors.market_unavailable() from exc

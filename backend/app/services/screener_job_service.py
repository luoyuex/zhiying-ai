"""主力选股后台任务：Redis 状态机 + ARQ worker 执行。

同步等待 4 次 LLM 调用容易超时，且刷新会丢进度；这里改成后台任务，
HTTP 只负责创建/查询，刷新后可通过活跃任务续上轮询。
"""

import asyncio
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.client import (
    LLMNotConfiguredError,
    LLMRateLimitedError,
    LLMRequestError,
    LLMResponseError,
    is_llm_configured,
)
from app.providers.base import DataNotFound, ProviderSchemaDrift, ProviderUnavailable
from app.schemas.ai import AIJobStatus
from app.schemas.screener import (
    LowPriceBullAnalysisRequest,
    MainForceAnalysisRequest,
    ProfitGrowthAnalysisRequest,
    ScreenerJobState,
    SmallCapAnalysisRequest,
    ValueStockAnalysisRequest,
)
from app.services.ai_analysis_service import (
    QuotaExceededError,
    QuotaServiceError,
    read_quota_used,
    seconds_to_midnight,
)
from app.services.ai_job_service import (
    AIWorkerUnavailableError,
    get_arq_pool,
    worker_alive,
)
from app.services.main_force_analysis_service import (
    MainForceEmptyError,
    analyze_low_price_bull,
    analyze_main_force,
    analyze_profit_growth,
    analyze_small_cap,
)
from app.services.screener_history_service import save_screener_record
from app.services.value_stock_service import analyze_value_stock

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
_TASKS: set[asyncio.Task] = set()

JOB_TTL_SECONDS = settings.llm_job_ttl_seconds
STALE_SECONDS = settings.llm_job_timeout_seconds + 120


class ScreenerJobNotFoundError(Exception):
    pass


class ScreenerJobForbiddenError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(TZ_SHANGHAI)


def _job_key(job_id: str) -> str:
    return f"screener:job:{job_id}"


def _active_key(user_id: object, strategy: str) -> str:
    return f"screener:active:{user_id}:{strategy}"


def _with_elapsed(state: ScreenerJobState) -> ScreenerJobState:
    if state.status in (AIJobStatus.QUEUED, AIJobStatus.RUNNING):
        elapsed = max(0, int((_now() - state.created_at).total_seconds()))
    else:
        elapsed = max(0, int((state.updated_at - state.created_at).total_seconds()))
    return state.model_copy(update={"elapsed_seconds": elapsed})


async def _save_state(
    redis: Redis,
    user_id: object,
    state: ScreenerJobState,
) -> ScreenerJobState:
    state = _with_elapsed(state)
    payload = {
        "user_id": str(user_id),
        "state": state.model_dump(mode="json"),
    }
    await redis.set(
        _job_key(state.job_id),
        json.dumps(payload, ensure_ascii=False),
        ex=JOB_TTL_SECONDS,
    )
    return state


async def _load_state(
    redis: Redis,
    job_id: str,
) -> tuple[str, ScreenerJobState] | None:
    try:
        raw = await redis.get(_job_key(job_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取选股任务失败: %s", exc)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return str(payload["user_id"]), ScreenerJobState.model_validate(payload["state"])
    except (ValueError, KeyError, TypeError):
        logger.warning("选股任务内容损坏 job_id=%s", job_id)
        return None


async def _update_state(
    redis: Redis,
    job_id: str,
    user_id: object,
    **changes,
) -> ScreenerJobState | None:
    loaded = await _load_state(redis, job_id)
    if loaded is None:
        return None
    _, state = loaded
    state = state.model_copy(update={**changes, "updated_at": _now()})
    return await _save_state(redis, user_id, state)


async def get_screener_job(
    redis: Redis,
    user_id: object,
    job_id: str,
) -> ScreenerJobState:
    loaded = await _load_state(redis, job_id)
    if loaded is None:
        raise ScreenerJobNotFoundError("选股任务不存在或已过期")
    owner, state = loaded
    if owner != str(user_id):
        raise ScreenerJobForbiddenError("无权查看该选股任务")

    if state.status in (AIJobStatus.QUEUED, AIJobStatus.RUNNING):
        idle_seconds = (_now() - state.updated_at).total_seconds()
        if idle_seconds > STALE_SECONDS:
            state = state.model_copy(
                update={
                    "status": AIJobStatus.FAILED,
                    "phase": "已中断",
                    "error_code": "SCREENER_JOB_STALE",
                    "error_message": "选股任务已中断（服务可能重启），请重新发起",
                    "updated_at": _now(),
                }
            )
            state = await _save_state(redis, user_id, state)
    return _with_elapsed(state)


async def get_active_screener_job(
    redis: Redis,
    user_id: object,
    strategy: str,
) -> ScreenerJobState | None:
    job_id = await redis.get(_active_key(user_id, strategy))
    if not job_id:
        return None
    try:
        return await get_screener_job(redis, user_id, str(job_id))
    except (ScreenerJobNotFoundError, ScreenerJobForbiddenError):
        return None


async def start_screener_job(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    strategy: str,
    payload: MainForceAnalysisRequest
    | LowPriceBullAnalysisRequest
    | SmallCapAnalysisRequest
    | ProfitGrowthAnalysisRequest
    | ValueStockAnalysisRequest,
) -> ScreenerJobState:
    if not is_llm_configured():
        raise LLMNotConfiguredError("尚未配置 LLM")

    active_job_id = await redis.get(_active_key(user_id, strategy))
    if active_job_id:
        loaded = await _load_state(redis, str(active_job_id))
        if loaded is not None and loaded[0] == str(user_id):
            state = loaded[1]
            if state.status in (AIJobStatus.QUEUED, AIJobStatus.RUNNING):
                return _with_elapsed(state)
        await redis.delete(_active_key(user_id, strategy))

    quota_used = await read_quota_used(redis, user_id, strict=True)
    if quota_used >= daily_quota:
        raise QuotaExceededError(daily_quota, seconds_to_midnight())

    if settings.ai_job_execution == "arq" and not await worker_alive(redis):
        raise AIWorkerUnavailableError("选股队列未启动，请先运行 npm run worker")

    job_id = uuid.uuid4().hex
    now = _now()
    state = ScreenerJobState(
        job_id=job_id,
        strategy=strategy,
        status=AIJobStatus.QUEUED,
        phase="排队中",
        created_at=now,
        updated_at=now,
    )
    await _save_state(redis, user_id, state)
    await redis.set(_active_key(user_id, strategy), job_id, ex=JOB_TTL_SECONDS)
    filters = payload.model_dump(mode="json")

    if settings.ai_job_execution == "arq":
        try:
            pool = await get_arq_pool()
            await pool.enqueue_job(
                "run_screener_job",
                job_id,
                str(user_id),
                daily_quota,
                strategy,
                filters,
                _job_id=job_id,
            )
        except Exception as exc:  # noqa: BLE001 - 入队失败要给出明确错误
            logger.exception("选股任务入队失败 job_id=%s: %s", job_id, exc)
            await redis.delete(_job_key(job_id))
            await redis.delete(_active_key(user_id, strategy))
            raise AIWorkerUnavailableError("选股队列暂时不可用，请稍后重试") from exc
        return state

    task = asyncio.create_task(
        run_screener_job_task(
            redis,
            job_id,
            str(user_id),
            daily_quota,
            strategy,
            filters,
        ),
        name=f"screener-job-{job_id}",
    )
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return state


async def run_screener_job_task(
    redis: Redis,
    job_id: str,
    user_id: str,
    daily_quota: int,
    strategy: str,
    filters: dict,
) -> None:
    """ARQ worker 入口，也用于 inline 模式。"""
    await _run_job(redis, job_id, user_id, daily_quota, strategy, filters)


async def _fail(
    redis: Redis,
    job_id: str,
    user_id: object,
    code: str,
    message: str,
) -> None:
    await _update_state(
        redis,
        job_id,
        user_id,
        status=AIJobStatus.FAILED,
        phase="失败",
        error_code=code,
        error_message=message,
    )


async def _run_job(
    redis: Redis,
    job_id: str,
    user_id: str,
    daily_quota: int,
    strategy: str,
    filters: dict,
) -> None:
    await _update_state(
        redis,
        job_id,
        user_id,
        status=AIJobStatus.RUNNING,
        phase="准备中",
    )
    user_uuid = uuid.UUID(user_id)

    async def on_phase(phase: str) -> None:
        await _update_state(redis, job_id, user_id, phase=phase)

    try:
        if strategy == "main_force":
            request = MainForceAnalysisRequest.model_validate(filters)
            result = await analyze_main_force(
                redis,
                user_uuid,
                daily_quota,
                request,
                on_phase=on_phase,
            )
        elif strategy == "low_price_bull":
            low_price_request = LowPriceBullAnalysisRequest.model_validate(filters)
            result = await analyze_low_price_bull(
                redis,
                user_uuid,
                daily_quota,
                low_price_request,
                on_phase=on_phase,
            )
        elif strategy == "small_cap":
            small_cap_request = SmallCapAnalysisRequest.model_validate(filters)
            result = await analyze_small_cap(
                redis,
                user_uuid,
                daily_quota,
                small_cap_request,
                on_phase=on_phase,
            )
        elif strategy == "profit_growth":
            profit_growth_request = ProfitGrowthAnalysisRequest.model_validate(filters)
            result = await analyze_profit_growth(
                redis,
                user_uuid,
                daily_quota,
                profit_growth_request,
                on_phase=on_phase,
            )
        elif strategy == "value_stock":
            value_request = ValueStockAnalysisRequest.model_validate(filters)
            result = await analyze_value_stock(
                redis,
                user_uuid,
                daily_quota,
                value_request,
                on_phase=on_phase,
            )
        else:
            raise ValueError(f"未知选股策略: {strategy}")

        await _update_state(redis, job_id, user_id, phase="保存选股记录")
        record_id = await save_screener_record(
            user_uuid,
            strategy,
            filters,
            result,
        )
        await _update_state(
            redis,
            job_id,
            user_id,
            status=AIJobStatus.SUCCEEDED,
            phase="已完成",
            record_id=record_id,
        )
    except MainForceEmptyError as exc:
        await _fail(redis, job_id, user_id, "SCREENER_EMPTY", str(exc))
    except QuotaExceededError as exc:
        await _fail(
            redis,
            job_id,
            user_id,
            "ANALYSIS_QUOTA_EXCEEDED",
            f"今日分析额度已用完（{exc.limit} 次），请明日再试",
        )
    except QuotaServiceError as exc:
        await _fail(redis, job_id, user_id, "AI_SERVICE_UNAVAILABLE", str(exc))
    except LLMNotConfiguredError:
        await _fail(redis, job_id, user_id, "LLM_NOT_CONFIGURED", "AI 服务未配置")
    except LLMRateLimitedError as exc:
        logger.warning("选股任务限流 job_id=%s: %s", job_id, exc)
        await _fail(redis, job_id, user_id, "LLM_BUSY", "AI 服务繁忙，请稍后重试")
    except LLMResponseError as exc:
        logger.warning("选股任务返回异常 job_id=%s: %s", job_id, exc)
        await _fail(
            redis,
            job_id,
            user_id,
            "LLM_INVALID_RESPONSE",
            "AI 返回结果异常，请稍后重试",
        )
    except LLMRequestError as exc:
        logger.warning("选股任务调用失败 job_id=%s: %s", job_id, exc)
        await _fail(
            redis,
            job_id,
            user_id,
            "LLM_ERROR",
            "AI 服务暂不可用，请稍后重试",
        )
    except (ProviderUnavailable, DataNotFound, ProviderSchemaDrift) as exc:
        logger.warning("选股任务数据不可用 job_id=%s: %s", job_id, exc)
        await _fail(
            redis,
            job_id,
            user_id,
            "MARKET_UNAVAILABLE",
            "行情/资金流数据暂不可用，请稍后重试",
        )
    except Exception as exc:  # noqa: BLE001 - worker 不能静默失败
        logger.exception("选股任务失败 job_id=%s: %s", job_id, exc)
        await _fail(
            redis,
            job_id,
            user_id,
            "SCREENER_JOB_FAILED",
            "AI 选股失败，请稍后重试",
        )

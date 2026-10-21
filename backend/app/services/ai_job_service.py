"""AI 分析后台任务：Redis 状态机 + 进程内 runner。

LLM 可能耗时数分钟，HTTP 请求只负责创建任务；进度通过 SSE（Redis Pub/Sub）
或轮询读取。后续迁移到 ARQ 时，保持 job 状态结构不变即可。
"""

import asyncio
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.client import (
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitedError,
    LLMRequestError,
    LLMResponseError,
    is_llm_configured,
)
from app.providers.base import DataNotFound, MarketUnavailable
from app.providers.financial import get_financial_data
from app.providers.fundflow import get_fund_flow
from app.providers.models import Adjust, KlinePeriod
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.ai import AIJobState, AIJobStatus
from app.services.ai_analysis_service import (
    QuotaExceededError,
    QuotaServiceError,
    cache_ai_report,
    generate_ai_analysis,
    get_cached_ai_report,
)
from app.services.market_service import MarketDataService
from app.services.report_history_service import save_analysis_report
from app.services.sentiment_service import build_sentiment_data
from app.services.technical_analysis import InsufficientDataError, analyze_technicals
from app.services.web_search_service import search_symbol_web

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
_TASKS: set[asyncio.Task] = set()

# worker 心跳：API 据此判断队列是否有人在消费
WORKER_HEARTBEAT_KEY = "ai:worker:alive"
_ARQ_POOL: ArqRedis | None = None
_ARQ_LOCK = asyncio.Lock()


class AIJobNotFoundError(Exception):
    pass


class AIJobForbiddenError(Exception):
    pass


class AIWorkerUnavailableError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(TZ_SHANGHAI)


def _job_key(job_id: str) -> str:
    return f"ai:job:{job_id}"


def _active_key(user_id: object, symbol: str) -> str:
    return f"ai:active:{user_id}:{symbol}"


def _with_elapsed(state: AIJobState) -> AIJobState:
    elapsed = max(0, int((_now() - state.created_at).total_seconds()))
    return state.model_copy(update={"elapsed_seconds": elapsed})


def job_events_channel(job_id: str) -> str:
    """SSE 事件通道：job 状态每次落 Redis 后向订阅者广播。"""
    return f"ai:job:events:{job_id}"


async def _get_arq_pool() -> ArqRedis:
    global _ARQ_POOL
    if _ARQ_POOL is None:
        async with _ARQ_LOCK:
            if _ARQ_POOL is None:
                _ARQ_POOL = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _ARQ_POOL


async def close_arq_pool() -> None:
    global _ARQ_POOL
    if _ARQ_POOL is not None:
        await _ARQ_POOL.aclose()
        _ARQ_POOL = None


async def worker_alive(redis: Redis) -> bool:
    try:
        return bool(await redis.exists(WORKER_HEARTBEAT_KEY))
    except Exception as exc:  # noqa: BLE001
        logger.warning("检查 ARQ worker 心跳失败: %s", exc)
        return False


async def _save_state(
    redis: Redis,
    job_id: str,
    user_id: object,
    state: AIJobState,
) -> AIJobState:
    state = _with_elapsed(state)
    payload = {
        "user_id": str(user_id),
        "state": state.model_dump(mode="json"),
    }
    await redis.set(
        _job_key(job_id),
        json.dumps(payload, ensure_ascii=False),
        ex=settings.llm_job_ttl_seconds,
    )
    try:
        await redis.publish(job_events_channel(job_id), state.model_dump_json())
    except Exception as exc:  # noqa: BLE001 - 推送失败不影响任务本身
        logger.warning("发布 AI job 事件失败 job_id=%s: %s", job_id, exc)
    return state


async def _load_state(redis: Redis, job_id: str) -> tuple[str, AIJobState] | None:
    try:
        raw = await redis.get(_job_key(job_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 AI job 失败: %s", exc)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return str(payload["user_id"]), AIJobState.model_validate(payload["state"])
    except (ValueError, KeyError, TypeError):
        logger.warning("AI job 内容损坏 job_id=%s", job_id)
        return None


async def _update_state(
    redis: Redis,
    job_id: str,
    user_id: object,
    **changes,
) -> AIJobState | None:
    loaded = await _load_state(redis, job_id)
    if loaded is None:
        return None
    _, state = loaded
    state = state.model_copy(update={**changes, "updated_at": _now()})
    return await _save_state(redis, job_id, user_id, state)


async def get_ai_job(redis: Redis, user_id: object, job_id: str) -> AIJobState:
    loaded = await _load_state(redis, job_id)
    if loaded is None:
        raise AIJobNotFoundError("分析任务不存在或已过期")
    owner, state = loaded
    if owner != str(user_id):
        raise AIJobForbiddenError("无权查看该分析任务")

    if state.status in (AIJobStatus.QUEUED, AIJobStatus.RUNNING):
        idle_seconds = (_now() - state.updated_at).total_seconds()
        if idle_seconds > settings.llm_job_timeout_seconds + 60:
            state = state.model_copy(
                update={
                    "status": AIJobStatus.FAILED,
                    "phase": "已中断",
                    "error_code": "AI_JOB_STALE",
                    "error_message": "分析任务已中断（服务可能重启），请重新发起",
                    "updated_at": _now(),
                }
            )
            state = await _save_state(redis, job_id, user_id, state)

    return _with_elapsed(state)


async def start_ai_job(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    symbol: str,
    force: bool = False,
) -> AIJobState:
    if not is_llm_configured():
        raise LLMNotConfiguredError("尚未配置 LLM")

    symbol = parse_symbol(symbol).code

    active_job_id = await redis.get(_active_key(user_id, symbol))
    if active_job_id:
        try:
            return await get_ai_job(redis, user_id, active_job_id)
        except (AIJobNotFoundError, AIJobForbiddenError):
            pass

    if settings.ai_job_execution == "arq" and not await worker_alive(redis):
        raise AIWorkerUnavailableError("分析队列未启动，请先运行 npm run worker")

    job_id = uuid.uuid4().hex
    now = _now()
    state = AIJobState(
        job_id=job_id,
        status=AIJobStatus.QUEUED,
        symbol=symbol,
        phase="排队中",
        created_at=now,
        updated_at=now,
    )
    await _save_state(redis, job_id, user_id, state)
    await redis.set(
        _active_key(user_id, symbol),
        job_id,
        ex=settings.llm_active_job_ttl_seconds,
    )

    if settings.ai_job_execution == "arq":
        try:
            pool = await _get_arq_pool()
            await pool.enqueue_job(
                "run_ai_job",
                job_id,
                str(user_id),
                daily_quota,
                symbol,
                force,
                _job_id=job_id,
            )
        except Exception as exc:  # noqa: BLE001 - 入队失败要让用户看到明确错误
            logger.exception("AI 任务入队失败 job_id=%s: %s", job_id, exc)
            await redis.delete(_job_key(job_id))
            await redis.delete(_active_key(user_id, symbol))
            raise AIWorkerUnavailableError("分析队列暂时不可用，请稍后重试") from exc
        return state

    task = asyncio.create_task(
        _run_job(job_id, redis, user_id, daily_quota, symbol, force),
        name=f"ai-job-{job_id}",
    )
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return state


async def get_active_job(
    redis: Redis,
    user_id: object,
    raw_symbol: str,
) -> AIJobState | None:
    """返回该股票当前仍在运行的任务；没有活跃任务时返回 None。"""
    symbol = parse_symbol(raw_symbol).code
    job_id = await redis.get(_active_key(user_id, symbol))
    if not job_id:
        return None
    try:
        return await get_ai_job(redis, user_id, job_id)
    except (AIJobNotFoundError, AIJobForbiddenError):
        return None


async def run_ai_job_task(
    redis: Redis,
    job_id: str,
    user_id: object,
    daily_quota: int,
    symbol: str,
    force: bool = False,
) -> None:
    """ARQ worker 入口：复用同一套状态机。"""
    await _run_job(job_id, redis, user_id, daily_quota, symbol, force)


async def _run_job(
    job_id: str,
    redis: Redis,
    user_id: object,
    daily_quota: int,
    symbol: str,
    force: bool = False,
) -> None:
    try:
        await _update_state(
            redis,
            job_id,
            user_id,
            status=AIJobStatus.RUNNING,
            phase="准备行情数据",
        )
        market = MarketDataService(redis)
        quote = await market.get_quote(symbol)
        kline = await market.get_kline(
            symbol,
            period=KlinePeriod.DAY,
            adjust=Adjust.QFQ,
            limit=90,
        )
        technical = analyze_technicals(quote, kline.bars, kline.source)

        cached = (
            None
            if force
            else await get_cached_ai_report(redis, user_id, daily_quota, quote)
        )
        if cached is not None:
            await _update_state(
                redis,
                job_id,
                user_id,
                status=AIJobStatus.SUCCEEDED,
                phase="命中 6h 缓存",
                result=cached,
                error_code=None,
                error_message=None,
            )
            logger.info("AI job 命中缓存 job_id=%s symbol=%s", job_id, symbol)
            return

        web = None
        await _update_state(
            redis,
            job_id,
            user_id,
            phase="准备六维数据（财务/资金流/情绪/公开信息）",
        )
        tasks = [
            get_financial_data(redis, quote),
            get_fund_flow(redis, quote),
            build_sentiment_data(redis, quote, kline.bars, technical),
        ]
        if settings.wsa_search_configured:
            tasks.append(search_symbol_web(redis, quote))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        financial = results[0] if not isinstance(results[0], BaseException) else None
        fund_flow = results[1] if not isinstance(results[1], BaseException) else None
        sentiment = results[2] if not isinstance(results[2], BaseException) else None
        if settings.wsa_search_configured:
            web = results[3] if not isinstance(results[3], BaseException) else None
            if web is not None and not web.success:
                logger.warning("元宝搜索未返回结果: %s", web.error)
        for index, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning("六维数据获取失败 index=%s: %s", index, result)

        # 六位分析师可能几乎同时完成，串行写状态避免进度回退
        progress_lock = asyncio.Lock()

        async def report_progress(text: str) -> None:
            async with progress_lock:
                await _update_state(redis, job_id, user_id, phase=text)

        await _update_state(
            redis,
            job_id,
            user_id,
            phase="六位分析师分析中 0/6",
        )
        async with asyncio.timeout(settings.llm_job_timeout_seconds):
            result = await generate_ai_analysis(
                redis,
                user_id,
                daily_quota,
                quote,
                technical,
                kline.bars,
                financial=financial,
                fund_flow=fund_flow,
                sentiment=sentiment,
                web=web,
                progress=report_progress,
                force=force,
            )

        try:
            report_id = await save_analysis_report(user_id, result)
            result = result.model_copy(update={"report_id": str(report_id)})
            await cache_ai_report(redis, quote, result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("保存分析报告失败 job_id=%s: %s", job_id, exc)

        await _update_state(
            redis,
            job_id,
            user_id,
            status=AIJobStatus.SUCCEEDED,
            phase="完成",
            result=result,
            error_code=None,
            error_message=None,
        )
        logger.info("AI job 完成 job_id=%s symbol=%s cached=%s", job_id, symbol, result.cached)
    except QuotaExceededError as exc:
        await _fail(redis, job_id, user_id, "ANALYSIS_QUOTA_EXCEEDED", str(exc))
    except QuotaServiceError as exc:
        await _fail(redis, job_id, user_id, "AI_SERVICE_UNAVAILABLE", str(exc))
    except LLMNotConfiguredError as exc:
        await _fail(redis, job_id, user_id, "LLM_NOT_CONFIGURED", str(exc))
    except LLMRateLimitedError as exc:
        await _fail(redis, job_id, user_id, "LLM_BUSY", str(exc))
    except LLMResponseError as exc:
        await _fail(redis, job_id, user_id, "LLM_INVALID_RESPONSE", str(exc))
    except LLMRequestError as exc:
        await _fail(redis, job_id, user_id, "LLM_ERROR", str(exc))
    except LLMError as exc:
        await _fail(redis, job_id, user_id, "LLM_ERROR", str(exc))
    except TimeoutError:
        await _fail(
            redis,
            job_id,
            user_id,
            "LLM_TIMEOUT",
            f"LLM 分析超过 {settings.llm_job_timeout_seconds} 秒，请稍后重试",
        )
    except InvalidSymbolError as exc:
        await _fail(redis, job_id, user_id, "INVALID_SYMBOL", str(exc))
    except DataNotFound as exc:
        await _fail(redis, job_id, user_id, "STOCK_NOT_FOUND", str(exc))
    except MarketUnavailable:
        await _fail(redis, job_id, user_id, "MARKET_UNAVAILABLE", "行情源暂时不可用，请稍后重试")
    except InsufficientDataError as exc:
        await _fail(redis, job_id, user_id, "ANALYSIS_UNAVAILABLE", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI job 未捕获异常 job_id=%s: %s", job_id, exc)
        await _fail(redis, job_id, user_id, "AI_SERVICE_UNAVAILABLE", "AI 分析失败，请稍后重试")
    finally:
        try:
            active_key = _active_key(user_id, symbol)
            current = await redis.get(active_key)
            if current == job_id:
                await redis.delete(active_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("清理 AI 活跃任务失败: %s", exc)


async def _fail(
    redis: Redis,
    job_id: str,
    user_id: object,
    code: str,
    message: str,
) -> None:
    logger.warning("AI job 失败 job_id=%s code=%s message=%s", job_id, code, message)
    await _update_state(
        redis,
        job_id,
        user_id,
        status=AIJobStatus.FAILED,
        phase="失败",
        error_code=code,
        error_message=message,
    )

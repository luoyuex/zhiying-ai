"""每日定时任务：自动选股与自动分析自选股（由 ARQ worker cron 周期触发）。

调度器每 5 分钟触发一次；每个用户按自己设置的执行时间（精确到分钟，
实际执行可能延迟至多 5 分钟）各自跑一轮，per-user 防重键保证当天只跑一次。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.automation_settings import AutomationSettings
from app.db.models.user import User
from app.db.models.watchlist import WatchlistItem
from app.db.session import SessionLocal
from app.llm.client import is_llm_configured
from app.schemas.automation import STRATEGY_FILTER_MODELS
from app.services.ai_analysis_service import QuotaExceededError, read_quota_used
from app.services.ai_job_service import AIWorkerUnavailableError, start_ai_job
from app.services.automation_run_log import (
    STATUS_ENQUEUED,
    STATUS_FAILED,
    STATUS_NO_TASKS,
    STATUS_QUOTA,
    record_run,
)
from app.services.screener_job_service import start_screener_job

logger = get_logger(__name__)

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 防重键 TTL：2 天，防时钟漂移与跨日边界
_RAN_KEY_TTL_SECONDS = 172_800


def _ran_key(now: datetime, user_id: object, task: str) -> str:
    return f"automation:ran:{now.strftime('%Y%m%d')}:{user_id}:{task}"


def _due(now: datetime, hour: int, minute: int) -> bool:
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now >= scheduled


async def run_daily_automation_task(redis) -> None:  # noqa: ANN001 - redis.asyncio.Redis
    if not is_llm_configured():
        return
    stats = await _collect_and_enqueue(redis)
    if stats["screener"] or stats["analysis"]:
        logger.info(
            "定时任务入队 选股=%s 分析=%s",
            stats["screener"],
            stats["analysis"],
        )


async def _load_enabled_users() -> list:  # noqa: ANN202
    """查询开启定时任务的 active 用户；测试通过覆盖本函数隔离真实账号。"""
    async with SessionLocal() as session:
        stmt = (
            select(User, AutomationSettings)
            .join(AutomationSettings, AutomationSettings.user_id == User.id)
            .where(
                User.status == "active",
                (AutomationSettings.screener_enabled.is_(True))
                | (AutomationSettings.analysis_enabled.is_(True)),
            )
        )
        return list((await session.execute(stmt)).all())


async def _collect_and_enqueue(redis) -> dict[str, int]:  # noqa: ANN001
    """查询开启定时任务的用户，到达各自执行时间的逐个入队；单用户失败不影响其他。"""
    stats = {"screener": 0, "analysis": 0}
    now = datetime.now(TZ_SHANGHAI)
    rows = await _load_enabled_users()

    for user, automation in rows:
        try:
            quota = settings.effective_daily_quota(user.daily_analysis_quota)
            if automation.screener_enabled and _due(
                now, automation.screener_run_hour, automation.screener_run_minute
            ):
                key = _ran_key(now, user.id, "screener")
                if await redis.set(key, "1", nx=True, ex=_RAN_KEY_TTL_SECONDS):
                    try:
                        count = await _enqueue_screener_jobs(
                            redis, user, quota, automation.strategy_settings or {}
                        )
                        stats["screener"] += count
                        if count:
                            await record_run(
                                user.id,
                                "screener",
                                STATUS_ENQUEUED,
                                enqueued=count,
                                now=now,
                            )
                        else:
                            await record_run(
                                user.id,
                                "screener",
                                STATUS_NO_TASKS,
                                reason="未启用任何策略",
                                now=now,
                            )
                    except QuotaExceededError:
                        await record_run(
                            user.id,
                            "screener",
                            STATUS_QUOTA,
                            reason="额度不足",
                            now=now,
                        )
                        raise
                    except AIWorkerUnavailableError:
                        await record_run(
                            user.id,
                            "screener",
                            STATUS_FAILED,
                            reason="分析队列不可用",
                            now=now,
                        )
                        raise
            if automation.analysis_enabled and _due(
                now, automation.analysis_run_hour, automation.analysis_run_minute
            ):
                key = _ran_key(now, user.id, "analysis")
                if await redis.set(key, "1", nx=True, ex=_RAN_KEY_TTL_SECONDS):
                    try:
                        count = await _enqueue_watchlist_analysis(redis, user, quota)
                        stats["analysis"] += count
                        if count:
                            await record_run(
                                user.id,
                                "analysis",
                                STATUS_ENQUEUED,
                                enqueued=count,
                                now=now,
                            )
                        else:
                            await record_run(
                                user.id,
                                "analysis",
                                STATUS_NO_TASKS,
                                reason="自选列表为空",
                                now=now,
                            )
                    except QuotaExceededError:
                        await record_run(
                            user.id,
                            "analysis",
                            STATUS_QUOTA,
                            reason="额度不足",
                            now=now,
                        )
                        raise
                    except AIWorkerUnavailableError:
                        await record_run(
                            user.id,
                            "analysis",
                            STATUS_FAILED,
                            reason="分析队列不可用",
                            now=now,
                        )
                        raise
        except QuotaExceededError:
            logger.info("定时任务跳过剩余项：额度已用完 user=%s", user.id)
        except AIWorkerUnavailableError as exc:
            logger.error("定时任务中止：队列不可用 user=%s: %s", user.id, exc)
            break
        except Exception as exc:  # noqa: BLE001 - 单用户失败不影响其他
            logger.exception("定时任务处理失败 user=%s: %s", user.id, exc)
    return stats


async def _enqueue_screener_jobs(
    redis,  # noqa: ANN001
    user: User,
    quota: int,
    strategy_settings: dict,
) -> int:
    enqueued = 0
    for strategy, setting in strategy_settings.items():
        if strategy not in STRATEGY_FILTER_MODELS:
            logger.warning("定时选股忽略未知策略 %s user=%s", strategy, user.id)
            continue
        if not isinstance(setting, dict) or not setting.get("enabled"):
            continue
        model = STRATEGY_FILTER_MODELS[strategy]
        payload = model.model_validate(setting.get("filters") or {})
        await start_screener_job(
            redis, user.id, quota, strategy, payload, trigger="scheduled"
        )
        enqueued += 1
    return enqueued


async def _watchlist_symbols(user_id: object) -> list[str]:
    async with SessionLocal() as session:
        stmt = (
            select(WatchlistItem.symbol)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.created_at.desc())
        )
        symbols = (await session.scalars(stmt)).all()
    return list(symbols)


async def _enqueue_watchlist_analysis(
    redis,  # noqa: ANN001
    user: User,
    quota: int,
) -> int:
    used = await read_quota_used(redis, user.id, strict=True)
    remaining = quota - used
    if remaining <= 0:
        raise QuotaExceededError(quota, 0)

    symbols = await _watchlist_symbols(user.id)
    if not symbols:
        return 0

    enqueued = 0
    for symbol in symbols:
        if enqueued >= remaining:
            break
        try:
            await start_ai_job(
                redis, user.id, quota, symbol, force=False, trigger="scheduled"
            )
            enqueued += 1
        except QuotaExceededError:
            raise
        except Exception as exc:  # noqa: BLE001 - 单只失败不影响其余自选
            logger.warning("定时分析入队失败 user=%s symbol=%s: %s", user.id, symbol, exc)
    return enqueued

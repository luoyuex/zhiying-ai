"""ARQ worker：在独立进程执行 AI 分析任务。

启动：
    uv run arq app.worker.WorkerSettings
根目录等价命令：npm run worker
"""

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.telemetry import start_telemetry, stop_telemetry
from app.db.redis import close_redis
from app.db.session import engine
from app.providers.http import close_http_client
from app.services.ai_job_service import (
    WORKER_HEARTBEAT_KEY,
    run_ai_job_task,
)
from app.services.daily_automation_service import run_daily_automation_task
from app.services.job_ledger import reconcile_stale_jobs
from app.services.screener_job_service import run_screener_job_task

logger = get_logger(__name__)

HEARTBEAT_TTL = settings.ai_worker_heartbeat_ttl_seconds


async def run_ai_job(
    ctx: dict,
    job_id: str,
    user_id: str,
    daily_quota: int,
    symbol: str,
    force: bool = False,
) -> None:
    await run_ai_job_task(ctx["redis"], job_id, user_id, daily_quota, symbol, force)


async def run_screener_job(
    ctx: dict,
    job_id: str,
    user_id: str,
    daily_quota: int,
    strategy: str,
    filters: dict,
) -> None:
    await run_screener_job_task(
        ctx["redis"], job_id, user_id, daily_quota, strategy, filters
    )


async def worker_heartbeat(ctx: dict) -> None:
    """供 API 判断是否有 worker 在消费队列。"""
    await ctx["redis"].set(WORKER_HEARTBEAT_KEY, "1", ex=HEARTBEAT_TTL)


async def run_daily_automation(ctx: dict) -> None:
    """每日定时选股 + 定时分析自选股（cron 触发，也可手动调用测试）。"""
    await run_daily_automation_task(ctx["redis"])


async def reconcile_jobs(ctx: dict) -> None:
    """把 worker 崩溃后长期停留的任务标为失败。"""
    count = await reconcile_stale_jobs(settings.llm_job_timeout_seconds + 120)
    if count:
        logger.info("回收中断任务 %s 条", count)


async def on_startup(ctx: dict) -> None:
    setup_logging(settings.debug, filename="worker.log")
    await start_telemetry()
    await worker_heartbeat(ctx)
    logger.info("ARQ worker 已启动 | max_jobs=%s", settings.ai_worker_max_jobs)


async def on_shutdown(ctx: dict) -> None:
    await stop_telemetry()
    await close_http_client()
    await close_redis()
    await engine.dispose()
    logger.info("ARQ worker 已关闭")


class WorkerSettings:
    functions = [run_ai_job, run_screener_job, run_daily_automation, reconcile_jobs]
    cron_jobs = [
        cron(worker_heartbeat, second={0, 30}, run_at_startup=True),
        # 每 5 分钟触发一次调度器；用户按各自设置的时间执行（per-user 防重键保证当天只跑一次）
        cron(
            run_daily_automation,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
            run_at_startup=True,
        ),
        cron(
            reconcile_jobs,
            minute={2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57},
            run_at_startup=True,
        ),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = settings.ai_worker_max_jobs
    job_timeout = settings.llm_job_timeout_seconds + 60
    max_tries = 1
    keep_result = 60
    health_check_interval = 30

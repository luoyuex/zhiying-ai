"""ARQ worker：在独立进程执行 AI 分析任务。

启动：
    uv run arq app.worker.WorkerSettings
根目录等价命令：npm run worker
"""

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.redis import close_redis
from app.db.session import engine
from app.providers.http import close_http_client
from app.services.ai_job_service import (
    WORKER_HEARTBEAT_KEY,
    run_ai_job_task,
)

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


async def worker_heartbeat(ctx: dict) -> None:
    """供 API 判断是否有 worker 在消费队列。"""
    await ctx["redis"].set(WORKER_HEARTBEAT_KEY, "1", ex=HEARTBEAT_TTL)


async def on_startup(ctx: dict) -> None:
    setup_logging(settings.debug)
    await worker_heartbeat(ctx)
    logger.info("ARQ worker 已启动 | max_jobs=%s", settings.ai_worker_max_jobs)


async def on_shutdown(ctx: dict) -> None:
    await close_http_client()
    await close_redis()
    await engine.dispose()
    logger.info("ARQ worker 已关闭")


class WorkerSettings:
    functions = [run_ai_job]
    cron_jobs = [cron(worker_heartbeat, second={0, 30}, run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = settings.ai_worker_max_jobs
    job_timeout = settings.llm_job_timeout_seconds + 60
    max_tries = 1
    keep_result = 60
    health_check_interval = 30

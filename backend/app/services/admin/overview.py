"""后台运营总览：只读本地 Postgres + Redis，不触发外部行情。"""

import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.ai_job import AIJob
from app.db.models.analysis_report import AnalysisReport
from app.db.models.llm_call import LLMCall
from app.db.models.portfolio_diagnosis import PortfolioDiagnosisRecord
from app.db.models.screener_record import ScreenerRecord
from app.db.models.user import User
from app.schemas.admin import (
    AdminOverview,
    AdminRecentFailure,
    AdminTopQuotaUser,
)
from app.services.ai_job_service import WORKER_HEARTBEAT_KEY

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
_ARQ_QUEUE_KEY = "arq:queue"


def _range_start(time_range: str) -> datetime:
    now = datetime.now(TZ_SHANGHAI)
    if time_range == "7d":
        return (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


async def _top_quota_users(
    db: AsyncSession, redis: Redis
) -> list[AdminTopQuotaUser]:
    today = datetime.now(TZ_SHANGHAI).strftime("%Y-%m-%d")
    keys: list[str] = []
    try:
        async for key in redis.scan_iter(match=f"ai:quota:*:{today}", count=200):
            keys.append(key)
            if len(keys) >= 2000:
                break
    except Exception:  # noqa: BLE001
        return []
    if not keys:
        return []

    try:
        pipe = redis.pipeline()
        for key in keys:
            pipe.get(key)
        values = await pipe.execute()
    except Exception:  # noqa: BLE001
        return []

    used_items: list[tuple[uuid.UUID, int]] = []
    for key, raw in zip(keys, values, strict=False):
        # ai:quota:{user_id}:{date}
        parts = key.split(":")
        if len(parts) < 4:
            continue
        user_id = _as_uuid(parts[2])
        if user_id is None:
            continue
        try:
            used = int(raw or 0)
        except (TypeError, ValueError):
            used = 0
        if used > 0:
            used_items.append((user_id, used))

    used_items.sort(key=lambda item: item[1], reverse=True)
    top = used_items[:5]
    if not top:
        return []

    user_ids = [item[0] for item in top]
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()
    user_map = {user.id: user for user in users}
    result = []
    for user_id, used in top:
        user = user_map.get(user_id)
        if user is None:
            continue
        result.append(
            AdminTopQuotaUser(
                user_id=user.id,
                email=user.email,
                nickname=user.nickname,
                used=used,
                quota=settings.effective_daily_quota(user.daily_analysis_quota),
            )
        )
    return result


async def _source_health(redis: Redis) -> tuple[int, int, int]:
    circuits = 0
    proxy_total = 0
    proxy_healthy = 0
    now = time.time()

    try:
        cb_keys = [key async for key in redis.scan_iter(match="mkt:cb:*", count=200)]
        if cb_keys:
            pipe = redis.pipeline()
            for key in cb_keys:
                pipe.hget(key, "open_until")
            values = await pipe.execute()
            circuits = sum(
                1
                for value in values
                if value and float(value) > now
            )
    except Exception:  # noqa: BLE001
        circuits = 0

    try:
        proxy_keys = [
            key
            async for key in redis.scan_iter(match="mkt:proxy:*", count=200)
            if ":ban:" not in key
        ]
        if proxy_keys:
            pipe = redis.pipeline()
            for key in proxy_keys:
                pipe.hgetall(key)
            rows = await pipe.execute()
            proxy_total = len(rows)
            proxy_healthy = sum(
                1
                for row in rows
                if int(row.get("ok") or 0) >= int(row.get("fail") or 0)
                and int(row.get("consecutive_fail") or 0) < 2
            )
    except Exception:  # noqa: BLE001
        proxy_total = 0
        proxy_healthy = 0

    return circuits, proxy_total, proxy_healthy


async def build_overview(
    db: AsyncSession,
    redis: Redis,
    time_range: str = "today",
) -> AdminOverview:
    since = _range_start(time_range)

    new_users = await db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= since)
    )

    active_union = union_all(
        select(AnalysisReport.user_id).where(AnalysisReport.created_at >= since),
        select(ScreenerRecord.user_id).where(ScreenerRecord.created_at >= since),
        select(PortfolioDiagnosisRecord.user_id).where(
            PortfolioDiagnosisRecord.created_at >= since
        ),
    ).subquery()
    active_users = await db.scalar(
        select(func.count(func.distinct(active_union.c.user_id)))
    )

    job_rows = (
        await db.execute(
            select(AIJob.status, func.count())
            .where(AIJob.created_at >= since)
            .group_by(AIJob.status)
        )
    ).all()
    job_counts = {status: int(count) for status, count in job_rows}
    jobs_total = sum(job_counts.values())
    jobs_succeeded = job_counts.get("succeeded", 0)
    jobs_failed = job_counts.get("failed", 0)

    token_sum, cost_sum = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0
                ),
                func.coalesce(func.sum(LLMCall.cost), 0),
            ).where(LLMCall.created_at >= since)
        )
    ).one()

    unpriced_calls = await db.scalar(
        select(func.count())
        .select_from(LLMCall)
        .where(
            LLMCall.created_at >= since,
            LLMCall.cost.is_(None),
            (LLMCall.prompt_tokens + LLMCall.completion_tokens) > 0,
        )
    )

    data_since = await db.scalar(select(func.min(LLMCall.created_at)))
    if data_since is None:
        data_since = await db.scalar(select(func.min(AIJob.created_at)))

    worker_alive = False
    queue_depth = 0
    try:
        worker_alive = bool(await redis.exists(WORKER_HEARTBEAT_KEY))
    except Exception:  # noqa: BLE001
        worker_alive = False
    try:
        queue_depth = int(await redis.llen(_ARQ_QUEUE_KEY) or 0)
    except Exception:  # noqa: BLE001
        queue_depth = 0

    running_jobs = await db.scalar(
        select(func.count()).select_from(AIJob).where(AIJob.status == "running")
    )
    circuits, proxy_total, proxy_healthy = await _source_health(redis)

    failure_rows = (
        await db.execute(
            select(AIJob, User.email)
            .outerjoin(User, User.id == AIJob.user_id)
            .where(AIJob.status == "failed")
            .order_by(AIJob.created_at.desc())
            .limit(5)
        )
    ).all()

    return AdminOverview(
        range=time_range,
        since=since,
        data_since=data_since,
        new_users=int(new_users or 0),
        active_users=int(active_users or 0),
        jobs_total=jobs_total,
        jobs_succeeded=jobs_succeeded,
        jobs_failed=jobs_failed,
        success_rate=(
            round(jobs_succeeded / jobs_total * 100, 1) if jobs_total else None
        ),
        tokens_total=int(token_sum or 0),
        cost_estimate=float(cost_sum or 0),
        unpriced_calls=int(unpriced_calls or 0),
        worker_alive=worker_alive,
        queue_depth=queue_depth,
        running_jobs=int(running_jobs or 0),
        open_circuits=circuits,
        proxy_total=proxy_total,
        proxy_healthy=proxy_healthy,
        quota_override_active=settings.ai_daily_quota_override > 0,
        top_quota_users=await _top_quota_users(db, redis),
        recent_failures=[
            AdminRecentFailure(
                job_id=row.id,
                kind=row.kind,
                user_email=email,
                symbol=row.symbol,
                strategy=row.strategy,
                error_code=row.error_code,
                error_message=row.error_message,
                created_at=row.created_at,
            )
            for row, email in failure_rows
        ],
    )

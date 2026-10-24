"""后台任务中心：查询任务台账，重跑失败任务。"""

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.ai_job import AIJob
from app.db.models.user import User
from app.llm.client import LLMNotConfiguredError
from app.schemas.admin import AdminJobDetail, AdminJobItem, AdminJobRetryResponse, Page
from app.schemas.automation import STRATEGY_FILTER_MODELS
from app.services.admin.audit import record_audit
from app.services.ai_analysis_service import QuotaExceededError
from app.services.ai_job_service import AIWorkerUnavailableError, start_ai_job
from app.services.screener_job_service import start_screener_job

logger = get_logger(__name__)


def _item(row: AIJob, email: str | None) -> AdminJobItem:
    return AdminJobItem(
        id=row.id,
        kind=row.kind,
        user_id=row.user_id,
        user_email=email,
        symbol=row.symbol,
        strategy=row.strategy,
        status=row.status,
        phase=row.phase,
        trigger=row.trigger,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        token_total=row.token_total,
        error_code=row.error_code,
        error_message=row.error_message,
        report_id=row.report_id,
        record_id=row.record_id,
    )


async def list_jobs(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    kind: str | None = None,
    status: str | None = None,
    trigger: str | None = None,
    q: str | None = None,
    date_from=None,
    date_to=None,
) -> Page[AdminJobItem]:
    stmt = select(AIJob, User.email).outerjoin(User, User.id == AIJob.user_id)
    count_stmt = select(func.count()).select_from(AIJob).outerjoin(
        User, User.id == AIJob.user_id
    )
    conditions = []
    if kind:
        conditions.append(AIJob.kind == kind)
    if status:
        conditions.append(AIJob.status == status)
    if trigger:
        conditions.append(AIJob.trigger == trigger)
    if q:
        keyword = q.strip().lower()
        conditions.append(
            func.lower(User.email).like(f"%{keyword}%")
            | AIJob.symbol.like(f"%{q.strip()}%")
            | AIJob.id.like(f"%{q.strip()}%")
        )
    if date_from:
        conditions.append(AIJob.created_at >= date_from)
    if date_to:
        conditions.append(AIJob.created_at <= date_to)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.execute(
            stmt.order_by(AIJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[_item(row.AIJob, row.email) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_job(db: AsyncSession, job_id: str) -> AdminJobDetail:
    row = (
        await db.execute(
            select(AIJob, User.email)
            .outerjoin(User, User.id == AIJob.user_id)
            .where(AIJob.id == job_id)
        )
    ).first()
    if row is None:
        raise errors.not_found("任务不存在")
    item = _item(row.AIJob, row.email)
    return AdminJobDetail(**item.model_dump(), meta=row.AIJob.meta)


async def retry_job(
    db: AsyncSession,
    redis: Redis,
    *,
    admin: User,
    job_id: str,
    ip: str | None = None,
    ua: str | None = None,
) -> AdminJobRetryResponse:
    row = (
        await db.execute(
            select(AIJob, User)
            .join(User, User.id == AIJob.user_id)
            .where(AIJob.id == job_id)
        )
    ).first()
    if row is None:
        raise errors.not_found("任务不存在")
    job: AIJob = row.AIJob
    user: User = row.User
    if job.status != "failed":
        raise errors.job_not_retryable(job.status)
    if user.status != "active":
        raise errors.validation("用户已被封禁，不能重跑任务")

    quota = settings.effective_daily_quota(user.daily_analysis_quota)
    try:
        if job.kind == "analysis":
            if not job.symbol:
                raise errors.validation("任务缺少股票代码，无法重跑")
            state = await start_ai_job(redis, user.id, quota, job.symbol, force=False)
        elif job.kind == "screener":
            if not job.strategy or job.strategy not in STRATEGY_FILTER_MODELS:
                raise errors.validation("任务缺少可用的选股策略，无法重跑")
            filters = (job.meta or {}).get("filters") or {}
            payload = STRATEGY_FILTER_MODELS[job.strategy].model_validate(filters)
            state = await start_screener_job(
                redis, user.id, quota, job.strategy, payload, trigger="manual"
            )
        else:
            raise errors.validation("未知任务类型，无法重跑")
    except LLMNotConfiguredError as exc:
        raise errors.llm_not_configured() from exc
    except QuotaExceededError as exc:
        raise errors.analysis_quota_exceeded(exc.limit, exc.reset_seconds) from exc
    except AIWorkerUnavailableError as exc:
        raise errors.ai_service_unavailable(str(exc)) from exc
    except ValueError as exc:
        raise errors.validation(f"任务参数不可用：{exc}") from exc

    await record_audit(
        admin=admin,
        action="job.retry",
        target_type="ai_job",
        target_id=job.id,
        before={"job_id": job.id, "status": job.status, "kind": job.kind},
        after={"new_job_id": state.job_id, "status": state.status.value},
        ip=ip,
        ua=ua,
        note=f"重跑失败任务 {job.kind}",
    )
    logger.info(
        "管理员重跑任务 admin=%s old=%s new=%s", admin.email, job.id, state.job_id
    )
    return AdminJobRetryResponse(
        job_id=state.job_id,
        status=state.status.value,
        message="已重新提交",
    )

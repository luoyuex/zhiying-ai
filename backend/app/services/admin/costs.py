"""后台成本日报：基于 llm_calls 的只读聚合。"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.llm_call import LLMCall
from app.db.models.user import User
from app.schemas.admin import (
    AdminCostCallItem,
    AdminCostDaily,
    AdminCostSummary,
    AdminCostTask,
    AdminCostUser,
    Page,
)

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _since(days: int) -> datetime:
    today = datetime.now(TZ_SHANGHAI).date()
    start = today - timedelta(days=days - 1)
    return datetime.combine(start, time.min, tzinfo=TZ_SHANGHAI)


def _tokens_expr():
    return func.coalesce(
        func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0
    )


def _cost_expr():
    return func.coalesce(func.sum(LLMCall.cost), 0)


def _float(value: object) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


async def build_cost_summary(db: AsyncSession, *, days: int = 14) -> AdminCostSummary:
    since = _since(days)

    day_expr = func.date_trunc(
        "day", func.timezone("Asia/Shanghai", LLMCall.created_at)
    )
    daily_rows = (
        await db.execute(
            select(
                day_expr.label("day"),
                func.count().label("calls"),
                _tokens_expr().label("tokens"),
                _cost_expr().label("cost"),
                func.count().filter(LLMCall.status != "success").label("failures"),
                func.count().filter(LLMCall.cost.is_(None)).label("unpriced"),
            )
            .where(LLMCall.created_at >= since)
            .group_by(day_expr)
            .order_by(day_expr)
        )
    ).all()

    buckets: dict[str, AdminCostDaily] = {}
    for row in daily_rows:
        day = row.day.date().isoformat()
        buckets[day] = AdminCostDaily(
            date=day,
            calls=int(row.calls or 0),
            failures=int(row.failures or 0),
            tokens=int(row.tokens or 0),
            cost=_float(row.cost),
        )

    daily: list[AdminCostDaily] = []
    cursor = since.date()
    today = datetime.now(TZ_SHANGHAI).date()
    while cursor <= today:
        key = cursor.isoformat()
        daily.append(buckets.get(key, AdminCostDaily(date=key)))
        cursor += timedelta(days=1)

    calls = sum(item.calls for item in daily)
    failures = sum(item.failures for item in daily)
    tokens = sum(item.tokens for item in daily)
    cost = round(sum(item.cost for item in daily), 4)
    unpriced = sum(int(row.unpriced or 0) for row in daily_rows)

    top_user_rows = (
        await db.execute(
            select(
                LLMCall.user_id,
                func.coalesce(User.email, "").label("email"),
                func.count().label("calls"),
                _tokens_expr().label("tokens"),
                _cost_expr().label("cost"),
            )
            .outerjoin(User, User.id == LLMCall.user_id)
            .where(LLMCall.created_at >= since)
            .group_by(LLMCall.user_id, User.email)
            .order_by(_cost_expr().desc(), func.count().desc())
            .limit(5)
        )
    ).all()
    top_users = [
        AdminCostUser(
            user_id=row.user_id,
            email=str(row.email or ""),
            calls=int(row.calls or 0),
            tokens=int(row.tokens or 0),
            cost=_float(row.cost),
        )
        for row in top_user_rows
    ]

    top_task_rows = (
        await db.execute(
            select(
                LLMCall.task,
                func.count().label("calls"),
                _tokens_expr().label("tokens"),
                _cost_expr().label("cost"),
            )
            .where(LLMCall.created_at >= since)
            .group_by(LLMCall.task)
            .order_by(_cost_expr().desc(), func.count().desc())
            .limit(8)
        )
    ).all()
    top_tasks = [
        AdminCostTask(
            task=str(row.task),
            calls=int(row.calls or 0),
            tokens=int(row.tokens or 0),
            cost=_float(row.cost),
        )
        for row in top_task_rows
    ]

    data_since = await db.scalar(select(func.min(LLMCall.created_at)))

    return AdminCostSummary(
        days=days,
        since=since,
        calls=calls,
        failures=failures,
        success_rate=round((calls - failures) / calls * 100, 1) if calls else None,
        tokens=tokens,
        cost=cost,
        unpriced_calls=unpriced,
        data_since=data_since,
        daily=daily,
        top_users=top_users,
        top_tasks=top_tasks,
    )


async def list_cost_calls(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    task: str | None = None,
    status: str | None = None,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Page[AdminCostCallItem]:
    stmt = select(LLMCall, User.email).outerjoin(User, User.id == LLMCall.user_id)
    count_stmt = select(func.count()).select_from(LLMCall).outerjoin(
        User, User.id == LLMCall.user_id
    )

    conditions = []
    if task:
        conditions.append(LLMCall.task == task)
    if status:
        conditions.append(LLMCall.status == status)
    if q:
        conditions.append(User.email.ilike(f"%{q.strip().lower()}%"))
    if date_from:
        conditions.append(LLMCall.created_at >= date_from)
    if date_to:
        conditions.append(LLMCall.created_at <= date_to)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.execute(
            stmt.order_by(LLMCall.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = [
        AdminCostCallItem(
            id=row.LLMCall.id,
            created_at=row.LLMCall.created_at,
            user_id=row.LLMCall.user_id,
            user_email=row.email,
            job_id=row.LLMCall.job_id,
            task=row.LLMCall.task,
            model=row.LLMCall.model,
            prompt_tokens=row.LLMCall.prompt_tokens,
            completion_tokens=row.LLMCall.completion_tokens,
            duration_ms=row.LLMCall.duration_ms,
            status=row.LLMCall.status,
            error_code=row.LLMCall.error_code,
            finish_reason=row.LLMCall.finish_reason,
            cost=float(row.LLMCall.cost) if row.LLMCall.cost is not None else None,
        )
        for row in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)

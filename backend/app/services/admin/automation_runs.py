"""后台定时执行记录查询。"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.automation_run import AutomationRun
from app.db.models.user import User
from app.schemas.admin import AdminAutomationRunItem, Page


async def list_automation_runs(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    run_date: date | None = None,
    line: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> Page[AdminAutomationRunItem]:
    stmt = select(AutomationRun, User.email).outerjoin(
        User, User.id == AutomationRun.user_id
    )
    count_stmt = select(func.count()).select_from(AutomationRun).outerjoin(
        User, User.id == AutomationRun.user_id
    )
    conditions = []
    if run_date:
        conditions.append(AutomationRun.run_date == run_date)
    if line:
        conditions.append(AutomationRun.line == line)
    if status:
        conditions.append(AutomationRun.status == status)
    if q:
        conditions.append(func.lower(User.email).like(f"%{q.strip().lower()}%"))
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.execute(
            stmt.order_by(
                AutomationRun.run_date.desc(), AutomationRun.created_at.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = [
        AdminAutomationRunItem(
            id=row.AutomationRun.id,
            run_date=row.AutomationRun.run_date.isoformat(),
            user_id=row.AutomationRun.user_id,
            user_email=row.email,
            line=row.AutomationRun.line,
            status=row.AutomationRun.status,
            enqueued=row.AutomationRun.enqueued,
            reason=row.AutomationRun.reason,
            created_at=row.AutomationRun.created_at,
        )
        for row in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)

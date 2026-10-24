"""后台定时任务执行记录接口。"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.common import PageParams
from app.core.deps import get_db
from app.schemas.admin import AdminAutomationRunItem, Page
from app.services.admin import automation_runs as automation_runs_service

router = APIRouter()


@router.get(
    "/automation-runs",
    response_model=Page[AdminAutomationRunItem],
    summary="定时任务执行记录",
)
async def list_automation_runs(
    params: PageParams = Depends(),
    run_date: date | None = None,
    line: Literal["screener", "analysis"] | None = None,
    status: Literal["enqueued", "no_tasks", "skipped_quota", "failed"] | None = None,
    q: str | None = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
) -> Page[AdminAutomationRunItem]:
    return await automation_runs_service.list_automation_runs(
        db,
        page=params.page,
        page_size=params.page_size,
        run_date=run_date,
        line=line,
        status=status,
        q=q,
    )

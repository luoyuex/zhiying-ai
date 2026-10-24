"""后台成本日报接口。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.common import PageParams
from app.core.deps import get_db
from app.schemas.admin import AdminCostCallItem, AdminCostSummary, Page
from app.services.admin import costs as costs_service

router = APIRouter()


@router.get(
    "/costs/summary",
    response_model=AdminCostSummary,
    summary="LLM 成本日报",
)
async def cost_summary(
    days: int = Query(14, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> AdminCostSummary:
    return await costs_service.build_cost_summary(db, days=days)


@router.get(
    "/costs/calls",
    response_model=Page[AdminCostCallItem],
    summary="LLM 调用明细",
)
async def cost_calls(
    params: PageParams = Depends(),
    task: str | None = Query(None, max_length=32),
    status: str | None = Query(None, max_length=16),
    q: str | None = Query(None, max_length=100),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminCostCallItem]:
    return await costs_service.list_cost_calls(
        db,
        page=params.page,
        page_size=params.page_size,
        task=task,
        status=status,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )

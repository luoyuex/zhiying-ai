"""后台任务中心接口：查询与重跑。"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.common import PageParams, client_ip, client_ua
from app.core.deps import get_db, require_admin
from app.db.models.user import User
from app.db.redis import get_redis
from app.schemas.admin import (
    AdminJobDetail,
    AdminJobItem,
    AdminJobRetryResponse,
    Page,
)
from app.services.admin import jobs as jobs_service

router = APIRouter()


@router.get("/jobs", response_model=Page[AdminJobItem], summary="任务列表")
async def list_jobs(
    params: PageParams = Depends(),
    kind: Literal["analysis", "screener"] | None = None,
    status: Literal["queued", "running", "succeeded", "failed"] | None = None,
    trigger: Literal["manual", "scheduled"] | None = None,
    q: str | None = Query(None, max_length=100),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminJobItem]:
    return await jobs_service.list_jobs(
        db,
        page=params.page,
        page_size=params.page_size,
        kind=kind,
        status=status,
        trigger=trigger,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/jobs/{job_id}", response_model=AdminJobDetail, summary="任务详情")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminJobDetail:
    return await jobs_service.get_job(db, job_id)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=AdminJobRetryResponse,
    summary="重跑失败任务",
)
async def retry_job(
    job_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AdminJobRetryResponse:
    return await jobs_service.retry_job(
        db,
        redis,
        admin=admin,
        job_id=job_id,
        ip=client_ip(request),
        ua=client_ua(request),
    )

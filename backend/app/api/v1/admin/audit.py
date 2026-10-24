from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.common import PageParams
from app.core.deps import get_db
from app.schemas.admin import AdminAuditLogItem, Page
from app.services.admin.audit import list_audit_logs

router = APIRouter()


@router.get(
    "/audit-logs",
    response_model=Page[AdminAuditLogItem],
    summary="管理员操作审计",
)
async def get_audit_logs(
    params: PageParams = Depends(),
    action: str | None = Query(None, max_length=64),
    target_type: str | None = Query(None, max_length=32),
    target_id: str | None = Query(None, max_length=64),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminAuditLogItem]:
    return await list_audit_logs(
        db,
        page=params.page,
        page_size=params.page_size,
        action=action,
        target_type=target_type,
        target_id=target_id,
        date_from=date_from,
        date_to=date_to,
    )

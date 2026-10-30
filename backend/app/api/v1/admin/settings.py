"""后台平台设置：新用户默认额度。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.common import client_ip, client_ua
from app.core.config import settings
from app.core.deps import get_db, require_admin
from app.db.models.user import User
from app.schemas.admin import (
    AdminQuotaPolicy,
    AdminQuotaPolicyResult,
    AdminQuotaPolicyUpdate,
)
from app.services.admin.audit import record_audit
from app.services.platform_settings_service import (
    get_default_daily_quota,
    set_default_daily_quota,
)

router = APIRouter()


def _policy(default_quota: int) -> AdminQuotaPolicy:
    return AdminQuotaPolicy(
        default_daily_quota=default_quota,
        override_active=settings.ai_daily_quota_override > 0,
        override_value=settings.ai_daily_quota_override,
    )


@router.get(
    "/quota-policy",
    response_model=AdminQuotaPolicy,
    summary="新用户默认额度",
)
async def get_quota_policy(db: AsyncSession = Depends(get_db)) -> AdminQuotaPolicy:
    return _policy(await get_default_daily_quota(db))


@router.put(
    "/quota-policy",
    response_model=AdminQuotaPolicyResult,
    summary="更新新用户默认额度",
)
async def update_quota_policy(
    payload: AdminQuotaPolicyUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminQuotaPolicyResult:
    before = await get_default_daily_quota(db)
    updated_users = await set_default_daily_quota(
        db,
        payload.default_daily_quota,
        admin_id=admin.id,
        apply_to_existing=payload.apply_to_existing,
    )
    await record_audit(
        admin=admin,
        action="quota.default.update",
        target_type="platform_setting",
        target_id="default_daily_quota",
        before={"default_daily_quota": before},
        after={
            "default_daily_quota": payload.default_daily_quota,
            "applied_to_existing": payload.apply_to_existing,
            "updated_users": updated_users,
        },
        ip=client_ip(request),
        ua=client_ua(request),
    )
    policy = _policy(payload.default_daily_quota)
    return AdminQuotaPolicyResult(
        **policy.model_dump(),
        updated_users=updated_users,
    )

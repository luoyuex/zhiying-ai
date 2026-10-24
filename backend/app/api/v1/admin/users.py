import uuid
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
    AdminResetQuotaResponse,
    AdminRevokeSessionsResponse,
    AdminSessionItem,
    AdminUserDetail,
    AdminUserListItem,
    AdminUserUpdate,
    Page,
)
from app.services.admin import users as users_service

router = APIRouter()


@router.get("/users", response_model=Page[AdminUserListItem], summary="用户列表")
async def list_users(
    params: PageParams = Depends(),
    q: str | None = Query(None, max_length=100),
    status: Literal["active", "banned"] | None = None,
    role: Literal["user", "admin"] | None = None,
    quota_min: int | None = Query(None, ge=0, le=100),
    quota_max: int | None = Query(None, ge=0, le=100),
    last_login_from: datetime | None = None,
    last_login_to: datetime | None = None,
    sort: Literal["created_at", "last_login_at", "daily_analysis_quota", "email"] = (
        "created_at"
    ),
    order: Literal["asc", "desc"] = "desc",
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Page[AdminUserListItem]:
    return await users_service.list_users(
        db,
        redis,
        page=params.page,
        page_size=params.page_size,
        q=q,
        status=status,
        role=role,
        quota_min=quota_min,
        quota_max=quota_max,
        last_login_from=last_login_from,
        last_login_to=last_login_to,
        sort=sort,
        order=order,
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetail,
    summary="用户详情",
)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AdminUserDetail:
    return await users_service.get_user_detail(db, redis, user_id)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserDetail,
    summary="调整用户额度或状态",
)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AdminUserDetail:
    return await users_service.update_user(
        db,
        redis,
        admin=admin,
        user_id=user_id,
        payload=payload,
        ip=client_ip(request),
        ua=client_ua(request),
    )


@router.post(
    "/users/{user_id}/reset-quota",
    response_model=AdminResetQuotaResponse,
    summary="重置用户今日已用额度",
)
async def reset_quota(
    user_id: uuid.UUID,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AdminResetQuotaResponse:
    return await users_service.reset_quota(
        db,
        redis,
        admin=admin,
        user_id=user_id,
        ip=client_ip(request),
        ua=client_ua(request),
    )


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=AdminRevokeSessionsResponse,
    summary="强制用户下线",
)
async def revoke_sessions(
    user_id: uuid.UUID,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminRevokeSessionsResponse:
    return await users_service.revoke_sessions(
        db,
        admin=admin,
        user_id=user_id,
        ip=client_ip(request),
        ua=client_ua(request),
    )


@router.get(
    "/users/{user_id}/sessions",
    response_model=Page[AdminSessionItem],
    summary="用户登录会话",
)
async def list_sessions(
    user_id: uuid.UUID,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Page[AdminSessionItem]:
    return await users_service.list_sessions(
        db,
        user_id=user_id,
        page=params.page,
        page_size=params.page_size,
    )

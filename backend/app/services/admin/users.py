"""后台用户查询与有限写操作。"""

import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.config import settings
from app.db.models.analysis_report import AnalysisReport
from app.db.models.automation_settings import AutomationSettings
from app.db.models.portfolio_diagnosis import PortfolioDiagnosisRecord
from app.db.models.refresh_token import RefreshToken
from app.db.models.screener_record import ScreenerRecord
from app.db.models.user import User
from app.db.models.watchlist import WatchlistItem
from app.schemas.admin import (
    AdminAutomationSummary,
    AdminRecentReport,
    AdminResetQuotaResponse,
    AdminRevokeSessionsResponse,
    AdminSessionItem,
    AdminUserCounts,
    AdminUserDetail,
    AdminUserListItem,
    AdminUserUpdate,
    Page,
)
from app.services.admin.audit import record_audit
from app.services.ai_analysis_service import quota_key


async def _get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise errors.not_found("用户不存在")
    return user


async def _read_today_used(redis: Redis, user_id: object) -> int:
    try:
        raw = await redis.get(quota_key(user_id))
        return int(raw or 0)
    except Exception:  # noqa: BLE001
        return 0


async def _reports_7d_counts(
    db: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not user_ids:
        return {}
    since = datetime.now(UTC) - timedelta(days=7)
    rows = (
        await db.execute(
            select(AnalysisReport.user_id, func.count())
            .where(
                AnalysisReport.user_id.in_(user_ids),
                AnalysisReport.created_at >= since,
            )
            .group_by(AnalysisReport.user_id)
        )
    ).all()
    return {user_id: int(count) for user_id, count in rows}


async def list_users(
    db: AsyncSession,
    redis: Redis,
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    status: str | None = None,
    role: str | None = None,
    quota_min: int | None = None,
    quota_max: int | None = None,
    last_login_from: datetime | None = None,
    last_login_to: datetime | None = None,
    sort: str = "created_at",
    order: str = "desc",
) -> Page[AdminUserListItem]:
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(or_(User.email.ilike(pattern), User.nickname.ilike(pattern)))
    if status:
        conditions.append(User.status == status)
    if role:
        conditions.append(User.role == role)
    if quota_min is not None:
        conditions.append(User.daily_analysis_quota >= quota_min)
    if quota_max is not None:
        conditions.append(User.daily_analysis_quota <= quota_max)
    if last_login_from is not None:
        conditions.append(User.last_login_at >= last_login_from)
    if last_login_to is not None:
        conditions.append(User.last_login_at <= last_login_to)

    total = await db.scalar(
        select(func.count()).select_from(User).where(*conditions)
    )
    sort_columns = {
        "created_at": User.created_at,
        "last_login_at": User.last_login_at,
        "daily_analysis_quota": User.daily_analysis_quota,
        "email": User.email,
    }
    column = sort_columns.get(sort, User.created_at)
    order_clause = column.asc() if order == "asc" else column.desc()
    offset = (page - 1) * page_size
    users = (
        await db.scalars(
            select(User)
            .where(*conditions)
            .order_by(order_clause)
            .offset(offset)
            .limit(page_size)
        )
    ).all()

    user_ids = [user.id for user in users]
    quota_values: list[str | None] = []
    if user_ids:
        try:
            quota_values = await redis.mget([quota_key(user_id) for user_id in user_ids])
        except Exception:  # noqa: BLE001
            quota_values = []
    report_counts = await _reports_7d_counts(db, user_ids)
    override_active = settings.ai_daily_quota_override > 0

    items = []
    for index, user in enumerate(users):
        used = 0
        if index < len(quota_values):
            try:
                used = int(quota_values[index] or 0)
            except (TypeError, ValueError):
                used = 0
        items.append(
            AdminUserListItem(
                id=user.id,
                email=user.email,
                nickname=user.nickname,
                role=user.role,
                status=user.status,
                daily_analysis_quota=user.daily_analysis_quota,
                effective_quota=settings.effective_daily_quota(user.daily_analysis_quota),
                quota_override_active=override_active,
                today_used=used,
                reports_7d=report_counts.get(user.id, 0),
                created_at=user.created_at,
                last_login_at=user.last_login_at,
            )
        )
    return Page(items=items, total=int(total or 0), page=page, page_size=page_size)


async def _count(db: AsyncSession, model, user_id: uuid.UUID) -> int:
    value = await db.scalar(
        select(func.count()).select_from(model).where(model.user_id == user_id)
    )
    return int(value or 0)


async def _automation_summary(
    db: AsyncSession, user_id: uuid.UUID
) -> AdminAutomationSummary:
    row = await db.scalar(
        select(AutomationSettings).where(AutomationSettings.user_id == user_id)
    )
    if row is None:
        return AdminAutomationSummary(
            screener_run_hour=settings.automation_cron_hour,
            screener_run_minute=settings.automation_cron_minute,
            analysis_run_hour=settings.automation_cron_hour,
            analysis_run_minute=settings.automation_cron_minute,
        )
    enabled_strategies = [
        strategy
        for strategy, value in (row.strategy_settings or {}).items()
        if isinstance(value, dict) and value.get("enabled")
    ]
    return AdminAutomationSummary(
        screener_enabled=row.screener_enabled,
        analysis_enabled=row.analysis_enabled,
        screener_run_hour=row.screener_run_hour,
        screener_run_minute=row.screener_run_minute,
        analysis_run_hour=row.analysis_run_hour,
        analysis_run_minute=row.analysis_run_minute,
        enabled_strategies=enabled_strategies,
        updated_at=row.updated_at,
    )


async def get_user_detail(
    db: AsyncSession,
    redis: Redis,
    user_id: uuid.UUID,
) -> AdminUserDetail:
    user = await _get_user(db, user_id)
    reports_7d = (await _reports_7d_counts(db, [user.id])).get(user.id, 0)
    counts = AdminUserCounts(
        reports=await _count(db, AnalysisReport, user.id),
        reports_7d=reports_7d,
        screener_records=await _count(db, ScreenerRecord, user.id),
        portfolio_diagnoses=await _count(db, PortfolioDiagnosisRecord, user.id),
        watchlist_items=await _count(db, WatchlistItem, user.id),
    )
    recent_rows = (
        await db.scalars(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user.id)
            .order_by(AnalysisReport.created_at.desc())
            .limit(5)
        )
    ).all()
    recent_reports = [
        AdminRecentReport(
            id=row.id,
            symbol=row.symbol,
            name=row.name,
            rating=row.rating,
            confidence=row.confidence,
            created_at=row.created_at,
        )
        for row in recent_rows
    ]
    return AdminUserDetail(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        role=user.role,
        status=user.status,
        email_verified_at=user.email_verified_at,
        daily_analysis_quota=user.daily_analysis_quota,
        effective_quota=settings.effective_daily_quota(user.daily_analysis_quota),
        quota_override_active=settings.ai_daily_quota_override > 0,
        today_used=await _read_today_used(redis, user.id),
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        counts=counts,
        automation=await _automation_summary(db, user.id),
        recent_reports=recent_reports,
    )


async def update_user(
    db: AsyncSession,
    redis: Redis,
    *,
    admin: User,
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    ip: str | None = None,
    ua: str | None = None,
) -> AdminUserDetail:
    target = await _get_user(db, user_id)
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise errors.validation("没有需要修改的字段")
    if updates.get("status") == "banned" and target.role == "admin":
        raise errors.validation("不能封禁管理员账号；如需停用请先通过 CLI 降级")

    before = {
        "status": target.status,
        "daily_analysis_quota": target.daily_analysis_quota,
    }
    for key, value in updates.items():
        setattr(target, key, value)
    await db.commit()
    await db.refresh(target)
    after = {
        "status": target.status,
        "daily_analysis_quota": target.daily_analysis_quota,
    }
    await record_audit(
        admin=admin,
        action="user.update",
        target_type="user",
        target_id=str(target.id),
        before=before,
        after=after,
        ip=ip,
        ua=ua,
    )
    return await get_user_detail(db, redis, target.id)


async def reset_quota(
    db: AsyncSession,
    redis: Redis,
    *,
    admin: User,
    user_id: uuid.UUID,
    ip: str | None = None,
    ua: str | None = None,
) -> AdminResetQuotaResponse:
    target = await _get_user(db, user_id)
    used_before = await _read_today_used(redis, target.id)
    try:
        await redis.delete(quota_key(target.id))
    except Exception as exc:  # noqa: BLE001
        raise errors.ai_service_unavailable("额度服务暂不可用，请稍后重试") from exc
    await record_audit(
        admin=admin,
        action="user.reset_quota",
        target_type="user",
        target_id=str(target.id),
        before={"today_used": used_before},
        after={"today_used": 0},
        ip=ip,
        ua=ua,
    )
    return AdminResetQuotaResponse(
        message=f"已重置 {target.email} 的今日额度",
        used_before=used_before,
    )


async def revoke_sessions(
    db: AsyncSession,
    *,
    admin: User,
    user_id: uuid.UUID,
    ip: str | None = None,
    ua: str | None = None,
) -> AdminRevokeSessionsResponse:
    target = await _get_user(db, user_id)
    now = datetime.now(UTC)
    active_before = await db.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.user_id == target.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
    )
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == target.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    await db.commit()
    revoked = int(result.rowcount or 0)
    await record_audit(
        admin=admin,
        action="user.revoke_sessions",
        target_type="user",
        target_id=str(target.id),
        before={"active_sessions": int(active_before or 0)},
        after={"revoked": revoked},
        ip=ip,
        ua=ua,
    )
    return AdminRevokeSessionsResponse(
        revoked=revoked,
        message="已撤销该用户全部刷新会话；已签发的访问令牌最多 15 分钟后失效",
    )


async def list_sessions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    page: int,
    page_size: int,
) -> Page[AdminSessionItem]:
    await _get_user(db, user_id)
    total = await db.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == user_id)
    )
    offset = (page - 1) * page_size
    rows = (
        await db.scalars(
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .order_by(RefreshToken.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()
    now = datetime.now(UTC)
    items = [
        AdminSessionItem(
            id=row.id,
            ip=row.ip,
            user_agent=row.user_agent,
            created_at=row.created_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            active=row.revoked_at is None and row.expires_at > now,
        )
        for row in rows
    ]
    return Page(
        items=items,
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )

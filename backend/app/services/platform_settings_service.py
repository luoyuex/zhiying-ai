"""平台级配置读写：目前用于后台可调整的新用户默认额度。"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.platform_setting import PlatformSetting
from app.db.models.user import User

logger = get_logger(__name__)

DEFAULT_QUOTA_KEY = "default_daily_quota"
# 未配置时的兜底值，与 users.daily_analysis_quota 的列默认值保持一致
FALLBACK_DEFAULT_QUOTA = 5
MIN_DAILY_QUOTA = 0
MAX_DAILY_QUOTA = 100


def _parse_quota(raw: str | None) -> int:
    if raw is None:
        return FALLBACK_DEFAULT_QUOTA
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return FALLBACK_DEFAULT_QUOTA
    return min(max(value, MIN_DAILY_QUOTA), MAX_DAILY_QUOTA)


async def get_default_daily_quota(db: AsyncSession) -> int:
    """新注册用户的默认每日额度；配置缺失或损坏时回退到 5 次。"""
    try:
        raw = await db.scalar(
            select(PlatformSetting.value).where(PlatformSetting.key == DEFAULT_QUOTA_KEY)
        )
    except Exception as exc:  # noqa: BLE001 - 配置表异常不能挡住注册
        logger.warning("读取新用户默认额度失败，回退到 %s: %s", FALLBACK_DEFAULT_QUOTA, exc)
        await db.rollback()
        return FALLBACK_DEFAULT_QUOTA
    return _parse_quota(raw)


async def set_default_daily_quota(
    db: AsyncSession,
    value: int,
    *,
    admin_id: object,
    apply_to_existing: bool = False,
) -> int:
    """保存默认额度，可选同步到现有普通用户；返回被同步的用户数。"""
    row = await db.get(PlatformSetting, DEFAULT_QUOTA_KEY)
    if row is None:
        db.add(
            PlatformSetting(
                key=DEFAULT_QUOTA_KEY,
                value=str(value),
                updated_by=admin_id,
            )
        )
    else:
        row.value = str(value)
        row.updated_by = admin_id

    updated_users = 0
    if apply_to_existing:
        # 管理员账号保留各自额度，只批量调整普通用户
        result = await db.execute(
            update(User)
            .where(User.role == "user")
            .values(daily_analysis_quota=value)
        )
        updated_users = int(result.rowcount or 0)

    await db.commit()
    return updated_users

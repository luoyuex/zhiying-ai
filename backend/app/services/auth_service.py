"""认证业务：注册、登录、会话轮换、登出、重置密码。"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors, security
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.refresh_token import RefreshToken
from app.db.models.user import User
from app.schemas.auth import RegisterRequest
from app.services.otp_service import OtpService
from app.services.platform_settings_service import get_default_daily_quota

logger = get_logger(__name__)


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == normalize_email(email)))


async def _create_session(
    db: AsyncSession,
    user: User,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """签发 access + refresh，返回 (access_token, 明文 refresh_token)。"""
    access_token = security.create_access_token(user.id, user.role)
    raw_refresh = security.new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=security.hash_refresh_token(raw_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            ip=ip,
            user_agent=(user_agent or "")[:500] or None,
        )
    )
    await db.flush()
    return access_token, raw_refresh


async def register(
    db: AsyncSession,
    otp: OtpService,
    payload: RegisterRequest,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str, str]:
    email = normalize_email(payload.email)

    if await get_user_by_email(db, email) is not None:
        raise errors.email_exists()

    await otp.verify(email, "register", payload.code)

    user = User(
        email=email,
        nickname=payload.nickname,
        password_hash=security.hash_password(payload.password),
        email_verified_at=datetime.now(UTC),
        last_login_at=datetime.now(UTC),
        # 新用户默认额度由后台配置决定，缺省 5 次/日
        daily_analysis_quota=await get_default_daily_quota(db),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise errors.email_exists() from exc

    access_token, raw_refresh = await _create_session(db, user, ip=ip, user_agent=user_agent)
    await db.commit()
    logger.info("user registered id=%s email=%s", user.id, email)
    return user, access_token, raw_refresh


async def login_with_password(
    db: AsyncSession,
    email: str,
    password: str,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str, str]:
    user = await get_user_by_email(db, email)

    if user is None or not user.password_hash:
        # 保持与正常路径相近的耗时，避免通过响应时间探测账号是否存在
        security.dummy_verify(password)
        raise errors.invalid_credentials()

    if not security.verify_password(password, user.password_hash):
        raise errors.invalid_credentials()

    if user.status != "active":
        raise errors.account_banned()

    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)

    user.last_login_at = datetime.now(UTC)
    access_token, raw_refresh = await _create_session(db, user, ip=ip, user_agent=user_agent)
    await db.commit()
    return user, access_token, raw_refresh


async def login_with_code(
    db: AsyncSession,
    otp: OtpService,
    email: str,
    code: str,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str, str]:
    email = normalize_email(email)
    await otp.verify(email, "login", code)

    user = await get_user_by_email(db, email)
    if user is None:
        raise errors.invalid_credentials()
    if user.status != "active":
        raise errors.account_banned()

    user.last_login_at = datetime.now(UTC)
    access_token, raw_refresh = await _create_session(db, user, ip=ip, user_agent=user_agent)
    await db.commit()
    return user, access_token, raw_refresh


async def reset_password(
    db: AsyncSession,
    otp: OtpService,
    email: str,
    code: str,
    new_password: str,
) -> None:
    email = normalize_email(email)
    await otp.verify(email, "reset", code)

    user = await get_user_by_email(db, email)
    if user is None:
        raise errors.invalid_credentials()

    user.password_hash = security.hash_password(new_password)
    await revoke_all_sessions(db, user.id)
    await db.commit()
    logger.info("password reset id=%s", user.id)


async def update_profile(db: AsyncSession, user: User, nickname: str) -> User:
    user.nickname = nickname.strip()
    await db.commit()
    await db.refresh(user)
    return user


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not user.password_hash or not security.verify_password(
        current_password, user.password_hash
    ):
        raise errors.AppError(
            errors.ErrorCode.INVALID_CREDENTIALS,
            "当前密码不正确",
            400,
        )
    if current_password == new_password:
        raise errors.AppError(
            errors.ErrorCode.VALIDATION_ERROR,
            "新密码不能与当前密码相同",
            400,
        )
    if new_password.lower() == user.email.split("@")[0].lower():
        raise errors.AppError(
            errors.ErrorCode.VALIDATION_ERROR,
            "密码不能与邮箱前缀相同",
            400,
        )
    user.password_hash = security.hash_password(new_password)
    await revoke_all_sessions(db, user.id)
    await db.commit()
    logger.info("password changed id=%s", user.id)


async def rotate_session(
    db: AsyncSession,
    raw_refresh: str | None,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str, str]:
    if not raw_refresh:
        raise errors.unauthorized()

    token_hash = security.hash_refresh_token(raw_refresh)
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if row is None:
        raise errors.unauthorized()

    now = datetime.now(UTC)

    if row.revoked_at is not None:
        # 旧 token 被重复使用：视为泄露，吊销该用户全部会话
        logger.warning("refresh token replay detected user_id=%s", row.user_id)
        await revoke_all_sessions(db, row.user_id)
        await db.commit()
        raise errors.unauthorized("检测到异常登录，请重新登录")

    if row.expires_at <= now:
        raise errors.unauthorized()

    user = await db.get(User, row.user_id)
    if user is None:
        raise errors.unauthorized()
    if user.status != "active":
        raise errors.account_banned()

    new_raw = security.new_refresh_token()
    new_row = RefreshToken(
        user_id=user.id,
        token_hash=security.hash_refresh_token(new_raw),
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        ip=ip,
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(new_row)
    await db.flush()

    row.revoked_at = now
    row.replaced_by = new_row.id

    access_token = security.create_access_token(user.id, user.role)
    await db.commit()
    return user, access_token, new_raw


async def logout(db: AsyncSession, raw_refresh: str | None) -> None:
    if not raw_refresh:
        return
    token_hash = security.hash_refresh_token(raw_refresh)
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await db.commit()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )

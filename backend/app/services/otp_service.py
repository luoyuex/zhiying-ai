"""邮箱验证码：生成、限流、一次性校验。

存储只落 Redis，不落数据库：
  otp:{purpose}:{email} -> {"hash": ..., "attempts": 0, "sent_at": "..."}  TTL 5 分钟
"""

import json
import secrets
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from app.core import errors
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_otp, verify_otp_hash

logger = get_logger(__name__)

PURPOSE_LABELS = {"register": "注册", "login": "登录", "reset": "重置密码"}


class OtpService:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    # ---------- key ----------
    @staticmethod
    def _code_key(purpose: str, email: str) -> str:
        return f"otp:{purpose}:{email}"

    @staticmethod
    def _cooldown_key(purpose: str, email: str) -> str:
        return f"otp:cd:{purpose}:{email}"

    @staticmethod
    def _email_limit_key(email: str) -> str:
        return f"otp:cnt:email:{email}:{datetime.now(UTC):%Y%m%d}"

    @staticmethod
    def _ip_limit_key(ip: str) -> str:
        return f"otp:cnt:ip:{ip}:{datetime.now(UTC):%Y%m%d%H}"

    # ---------- 发送 ----------
    async def issue(self, email: str, purpose: str, ip: str) -> tuple[str, int]:
        """返回 (明文验证码, 有效期秒数)。限流不通过直接抛 AppError。"""
        await self._guard_rate_limit(email, purpose, ip)

        code = f"{secrets.randbelow(1_000_000):06d}"
        payload = json.dumps(
            {
                "hash": hash_otp(purpose, email, code),
                "attempts": 0,
                "sent_at": datetime.now(UTC).isoformat(),
            }
        )
        await self.redis.set(self._code_key(purpose, email), payload, ex=settings.otp_ttl_seconds)
        logger.info("OTP issued purpose=%s email=%s", purpose, _mask_email(email))
        return code, settings.otp_ttl_seconds

    async def _guard_rate_limit(self, email: str, purpose: str, ip: str) -> None:
        cooldown_key = self._cooldown_key(purpose, email)
        acquired = await self.redis.set(
            cooldown_key, "1", nx=True, ex=settings.otp_cooldown_seconds
        )
        if not acquired:
            ttl = await self.redis.ttl(cooldown_key)
            retry_after = max(int(ttl), 1)
            raise errors.rate_limited(f"发送太频繁，请 {retry_after} 秒后再试", retry_after)

        email_key = self._email_limit_key(email)
        email_count = await self.redis.incr(email_key)
        if email_count == 1:
            await self.redis.expire(email_key, 86400)
        if email_count > settings.otp_email_daily_limit:
            raise errors.rate_limited("该邮箱今日获取验证码次数已达上限，请明天再试", _seconds_to_midnight())

        ip_key = self._ip_limit_key(ip)
        ip_count = await self.redis.incr(ip_key)
        if ip_count == 1:
            await self.redis.expire(ip_key, 3600)
        if ip_count > settings.otp_ip_hourly_limit:
            raise errors.rate_limited("当前网络获取验证码过于频繁，请稍后再试", 3600)

    # ---------- 校验 ----------
    async def verify(self, email: str, purpose: str, code: str) -> None:
        key = self._code_key(purpose, email)
        raw = await self.redis.get(key)
        if raw is None:
            raise errors.code_expired()

        try:
            data = json.loads(raw)
            expected_hash = data["hash"]
            attempts = int(data.get("attempts", 0))
        except (ValueError, KeyError) as exc:
            await self.redis.delete(key)
            raise errors.code_expired() from exc

        if attempts >= settings.otp_max_attempts:
            await self.redis.delete(key)
            raise errors.code_invalid(0)

        if not verify_otp_hash(purpose, email, code, expected_hash):
            attempts += 1
            remaining = max(settings.otp_max_attempts - attempts, 0)
            if remaining <= 0:
                await self.redis.delete(key)
                raise errors.code_invalid(0)
            data["attempts"] = attempts
            await self.redis.set(key, json.dumps(data), keepttl=True)
            raise errors.code_invalid(remaining)

        # 一次性使用
        await self.redis.delete(key)
        logger.info("OTP verified purpose=%s email=%s", purpose, _mask_email(email))


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    if len(name) <= 2:
        masked = name[:1] + "*"
    else:
        masked = name[:2] + "***" + name[-1:]
    return f"{masked}@{domain}"


def _seconds_to_midnight() -> int:
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((tomorrow - now).total_seconds()), 60)

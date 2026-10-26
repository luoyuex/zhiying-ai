"""用户头像：校验 data URL、压缩后二进制存库、按用户读取。"""

import base64
import binascii
import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import get_logger
from app.db.models.user import User
from app.db.models.user_avatar import UserAvatar
from app.db.session import SessionLocal

logger = get_logger(__name__)

MAX_AVATAR_BYTES = 512 * 1024
_ALLOWED_PREFIXES = {
    "data:image/jpeg;base64,": ("image/jpeg", (b"\xff\xd8\xff",)),
    "data:image/png;base64,": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    "data:image/webp;base64,": ("image/webp", (b"RIFF",)),
}


class AvatarInvalidError(ValueError):
    pass


def _decode_data_url(data_url: str) -> tuple[str, bytes]:
    text = (data_url or "").strip()
    for prefix, (content_type, signatures) in _ALLOWED_PREFIXES.items():
        if not text.startswith(prefix):
            continue
        payload = text[len(prefix) :]
        try:
            raw = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AvatarInvalidError("头像数据格式不正确") from exc
        if not raw:
            raise AvatarInvalidError("头像内容为空")
        if len(raw) > MAX_AVATAR_BYTES:
            raise AvatarInvalidError("头像不能超过 512 KB")
        if not any(raw.startswith(signature) for signature in signatures):
            raise AvatarInvalidError("头像文件格式不受支持")
        return content_type, raw
    raise AvatarInvalidError("仅支持 JPG、PNG 或 WebP 图片")


async def save_avatar(user_id: uuid.UUID, data_url: str) -> int:
    content_type, raw = _decode_data_url(data_url)
    async with SessionLocal() as session:
        stmt = (
            pg_insert(UserAvatar)
            .values(
                user_id=user_id,
                content_type=content_type,
                data=raw,
            )
            .on_conflict_do_update(
                index_elements=[UserAvatar.user_id],
                set_={
                    "content_type": content_type,
                    "data": raw,
                },
            )
        )
        await session.execute(stmt)
        user = await session.get(User, user_id)
        if user is None:
            raise AvatarInvalidError("用户不存在")
        version = (user.avatar_version or 0) + 1
        user.avatar_version = version
        await session.commit()
    logger.info("头像已更新 user=%s bytes=%s type=%s", user_id, len(raw), content_type)
    return version


async def delete_avatar(user_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(UserAvatar).where(UserAvatar.user_id == user_id))
        user = await session.get(User, user_id)
        if user is not None:
            user.avatar_version = 0
        await session.commit()


async def get_avatar(user_id: uuid.UUID) -> tuple[bytes, str] | None:
    async with SessionLocal() as session:
        row = await session.scalar(
            select(UserAvatar).where(UserAvatar.user_id == user_id)
        )
    if row is None:
        return None
    return bytes(row.data), row.content_type

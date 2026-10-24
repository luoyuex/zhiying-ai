"""管理员操作审计。写入失败只记日志，不阻断业务。"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.serialization import jsonable
from app.db.models.admin_audit_log import AdminAuditLog
from app.db.models.user import User
from app.db.session import SessionLocal
from app.schemas.admin import AdminAuditLogItem, Page

logger = get_logger(__name__)


async def record_audit(
    *,
    admin: User | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    before: Any = None,
    after: Any = None,
    result: str = "success",
    ip: str | None = None,
    ua: str | None = None,
    note: str | None = None,
) -> None:
    try:
        async with SessionLocal() as session:
            session.add(
                AdminAuditLog(
                    admin_user_id=admin.id if admin else None,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    before=jsonable(before),
                    after=jsonable(after),
                    result=result,
                    ip=ip,
                    ua=(ua or "")[:1000] or None,
                    note=(note or "")[:255] or None,
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入管理员审计失败 action=%s: %s", action, exc)


async def list_audit_logs(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    date_from=None,
    date_to=None,
) -> Page[AdminAuditLogItem]:
    conditions = []
    if action:
        conditions.append(AdminAuditLog.action == action)
    if target_type:
        conditions.append(AdminAuditLog.target_type == target_type)
    if target_id:
        conditions.append(AdminAuditLog.target_id == target_id)
    if date_from is not None:
        conditions.append(AdminAuditLog.created_at >= date_from)
    if date_to is not None:
        conditions.append(AdminAuditLog.created_at <= date_to)

    total = await db.scalar(
        select(func.count()).select_from(AdminAuditLog).where(*conditions)
    )
    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            select(AdminAuditLog, User.email)
            .outerjoin(User, User.id == AdminAuditLog.admin_user_id)
            .where(*conditions)
            .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()

    items = [
        AdminAuditLogItem(
            id=row.id,
            created_at=row.created_at,
            admin_email=email,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            before=row.before,
            after=row.after,
            result=row.result,
            ip=row.ip,
            ua=row.ua,
            note=row.note,
        )
        for row, email in rows
    ]
    return Page(
        items=items,
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )

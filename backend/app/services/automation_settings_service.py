"""定时任务设置：读取与更新用户级自动化配置。"""

import uuid

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import get_logger
from app.db.models.automation_settings import AutomationSettings
from app.db.session import SessionLocal
from app.schemas.automation import AutomationSettingsResponse, AutomationSettingsUpdate

logger = get_logger(__name__)


class AutomationFiltersInvalidError(Exception):
    """策略筛选参数校验失败。"""


def _to_response(row: AutomationSettings | None) -> AutomationSettingsResponse:
    if row is None:
        return AutomationSettingsResponse()
    return AutomationSettingsResponse(
        screener_enabled=row.screener_enabled,
        analysis_enabled=row.analysis_enabled,
        screener_run_hour=row.screener_run_hour,
        screener_run_minute=row.screener_run_minute,
        analysis_run_hour=row.analysis_run_hour,
        analysis_run_minute=row.analysis_run_minute,
        strategy_settings=row.strategy_settings or {},
        email_notify_enabled=row.email_notify_enabled,
        notify_email=row.notify_email,
        updated_at=row.updated_at,
    )


async def get_settings(user_id: uuid.UUID) -> AutomationSettingsResponse:
    async with SessionLocal() as session:
        stmt = select(AutomationSettings).where(AutomationSettings.user_id == user_id)
        row = (await session.scalars(stmt)).first()
    return _to_response(row)


async def update_settings(
    user_id: uuid.UUID,
    payload: AutomationSettingsUpdate,
) -> AutomationSettingsResponse:
    try:
        strategy_settings = payload.normalized_strategy_settings()
    except ValidationError as exc:
        raise AutomationFiltersInvalidError(str(exc)) from exc

    async with SessionLocal() as session:
        stmt = (
            pg_insert(AutomationSettings)
            .values(
                user_id=user_id,
                screener_enabled=payload.screener_enabled,
                analysis_enabled=payload.analysis_enabled,
                screener_run_hour=payload.screener_run_hour,
                screener_run_minute=payload.screener_run_minute,
                analysis_run_hour=payload.analysis_run_hour,
                analysis_run_minute=payload.analysis_run_minute,
                strategy_settings=strategy_settings,
                email_notify_enabled=payload.email_notify_enabled,
                notify_email=payload.notify_email,
            )
            .on_conflict_do_update(
                index_elements=[AutomationSettings.user_id],
                set_={
                    "screener_enabled": payload.screener_enabled,
                    "analysis_enabled": payload.analysis_enabled,
                    "screener_run_hour": payload.screener_run_hour,
                    "screener_run_minute": payload.screener_run_minute,
                    "analysis_run_hour": payload.analysis_run_hour,
                    "analysis_run_minute": payload.analysis_run_minute,
                    "strategy_settings": strategy_settings,
                    "email_notify_enabled": payload.email_notify_enabled,
                    "notify_email": payload.notify_email,
                    "updated_at": func.now(),
                },
            )
        )
        await session.execute(stmt)
        await session.commit()
        row = (await session.scalars(
            select(AutomationSettings).where(AutomationSettings.user_id == user_id)
        )).first()
    return _to_response(row)

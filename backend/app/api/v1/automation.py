"""定时任务设置接口：每日自动选股与自动分析自选股。"""

from fastapi import APIRouter, Depends

from app.core import errors
from app.core.deps import get_current_user
from app.db.models.user import User
from app.schemas.automation import (
    AutomationSettingsResponse,
    AutomationSettingsUpdate,
)
from app.services.automation_settings_service import (
    AutomationFiltersInvalidError,
    get_settings,
    update_settings,
)

router = APIRouter(prefix="/automation", tags=["定时任务"])


@router.get("/settings", response_model=AutomationSettingsResponse, summary="读取定时任务设置")
async def read_settings(user: User = Depends(get_current_user)) -> AutomationSettingsResponse:
    return await get_settings(user.id)


@router.put("/settings", response_model=AutomationSettingsResponse, summary="更新定时任务设置")
async def write_settings(
    payload: AutomationSettingsUpdate,
    user: User = Depends(get_current_user),
) -> AutomationSettingsResponse:
    try:
        return await update_settings(user.id, payload)
    except AutomationFiltersInvalidError as exc:
        raise errors.validation(f"策略筛选参数不合法: {exc}") from exc

"""定时任务执行记录写入：每个用户、每条任务线、每天覆盖为最新一次判定结果。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import get_logger
from app.db.models.automation_run import AutomationRun
from app.db.session import SessionLocal

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

STATUS_ENQUEUED = "enqueued"
STATUS_NO_TASKS = "no_tasks"
STATUS_QUOTA = "skipped_quota"
STATUS_FAILED = "failed"


async def record_run(
    user_id: object,
    line: str,
    status: str,
    *,
    enqueued: int = 0,
    reason: str | None = None,
    now: datetime | None = None,
) -> None:
    """写/更新当天该用户该任务线的执行结果；失败只记日志，不影响调度。"""
    current = (now or datetime.now(TZ_SHANGHAI)).astimezone(TZ_SHANGHAI)
    run_date: date = current.date()
    try:
        async with SessionLocal() as session:
            stmt = (
                pg_insert(AutomationRun)
                .values(
                    run_date=run_date,
                    user_id=user_id,
                    line=line,
                    status=status,
                    enqueued=enqueued,
                    reason=(reason or "")[:64] or None,
                    created_at=current,
                )
                .on_conflict_do_update(
                    constraint="uq_automation_runs_day_user_line",
                    set_={
                        "status": status,
                        "enqueued": enqueued,
                        "reason": (reason or "")[:64] or None,
                        "created_at": current,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - 台账失败不影响调度
        logger.warning(
            "写入定时执行记录失败 user=%s line=%s: %s", user_id, line, exc
        )

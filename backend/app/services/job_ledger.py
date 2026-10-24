"""AI 任务台账：Redis 负责实时进度，Postgres 负责可检索的历史。

所有写入都吞异常，台账失败不影响任务本身。
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Integer, cast, func, update

from app.core.logging import get_logger
from app.core.serialization import jsonable
from app.db.models.ai_job import AIJob
from app.db.session import SessionLocal

logger = get_logger(__name__)


def _as_uuid(value: object | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _duration_ms_expr():
    seconds = func.extract(
        "epoch", func.now() - func.coalesce(AIJob.started_at, AIJob.created_at)
    )
    return cast(seconds * 1000, Integer)


async def record_job_created(
    *,
    job_id: str,
    kind: str,
    user_id: object,
    symbol: str | None = None,
    strategy: str | None = None,
    trigger: str = "manual",
    phase: str = "排队中",
    meta: dict[str, Any] | None = None,
) -> None:
    owner = _as_uuid(user_id)
    if owner is None:
        return
    try:
        async with SessionLocal() as session:
            session.add(
                AIJob(
                    id=job_id,
                    kind=kind,
                    user_id=owner,
                    symbol=symbol,
                    strategy=strategy,
                    status="queued",
                    phase=phase,
                    trigger=trigger,
                    meta=jsonable(meta),
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入任务台账失败 job_id=%s: %s", job_id, exc)


async def record_job_running(job_id: str, phase: str = "") -> None:
    try:
        async with SessionLocal() as session:
            values: dict[str, Any] = {
                "status": "running",
                "started_at": func.now(),
            }
            if phase:
                values["phase"] = phase
            await session.execute(
                update(AIJob)
                .where(AIJob.id == job_id, AIJob.status.in_(["queued", "running"]))
                .values(**values)
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("更新任务台账失败 job_id=%s: %s", job_id, exc)


async def record_job_succeeded(
    job_id: str,
    *,
    phase: str = "完成",
    report_id: object | None = None,
    record_id: object | None = None,
) -> None:
    values: dict[str, Any] = {
        "status": "succeeded",
        "phase": phase,
        "finished_at": func.now(),
        "duration_ms": _duration_ms_expr(),
        "error_code": None,
        "error_message": None,
    }
    if report_id is not None:
        values["report_id"] = _as_uuid(report_id)
    if record_id is not None:
        values["record_id"] = _as_uuid(record_id)
    await _finish_job(job_id, values)


async def record_job_failed(
    job_id: str,
    *,
    error_code: str,
    error_message: str,
    phase: str = "失败",
) -> None:
    await _finish_job(
        job_id,
        {
            "status": "failed",
            "phase": phase,
            "finished_at": func.now(),
            "duration_ms": _duration_ms_expr(),
            "error_code": error_code,
            "error_message": error_message[:1000],
        },
    )


async def _finish_job(job_id: str, values: dict[str, Any]) -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(update(AIJob).where(AIJob.id == job_id).values(**values))
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("结束任务台账失败 job_id=%s: %s", job_id, exc)


async def reconcile_stale_jobs(max_age_seconds: int) -> int:
    """worker 重启或崩溃后，把长期停留在 queued/running 的任务标为失败。"""
    threshold = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                update(AIJob)
                .where(
                    AIJob.status.in_(["queued", "running"]),
                    func.coalesce(AIJob.started_at, AIJob.created_at) < threshold,
                )
                .values(
                    status="failed",
                    phase="已中断",
                    finished_at=func.now(),
                    duration_ms=_duration_ms_expr(),
                    error_code="JOB_STALE",
                    error_message="任务已中断（服务可能重启），请重新发起",
                )
            )
            await session.commit()
            return int(result.rowcount or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("回收中断任务失败: %s", exc)
        return 0

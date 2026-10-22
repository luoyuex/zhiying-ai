"""选股记录：落库、列表与详情。"""

import uuid

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.screener_record import ScreenerRecord
from app.db.session import SessionLocal
from app.schemas.screener import (
    MainForceAnalysisResponse,
    MainForceRecordDetail,
    MainForceRecordSummary,
    ScreenerRecordPick,
)

logger = get_logger(__name__)


async def save_screener_record(
    user_id: object,
    strategy: str,
    filters: dict,
    result: MainForceAnalysisResponse,
) -> uuid.UUID:
    async with SessionLocal() as session:
        row = ScreenerRecord(
            user_id=user_id,
            strategy=strategy,
            filters=filters,
            result=result.model_dump(mode="json"),
            analyzed_count=result.analyzed_count,
            recommendation_count=len(result.recommendations),
            model=result.model,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


def _summary(row: ScreenerRecord) -> MainForceRecordSummary:
    raw = row.result or {}
    filters = row.filters or {}
    picks: list[ScreenerRecordPick] = []
    for item in raw.get("recommendations") or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            continue
        picks.append(
            ScreenerRecordPick(
                rank=int(item.get("rank") or len(picks) + 1),
                symbol=symbol,
                name=str(item.get("name") or "").strip(),
            )
        )
    final_n = filters.get("final_n")
    max_change_pct = filters.get("max_change_pct")
    return MainForceRecordSummary(
        id=row.id,
        strategy=row.strategy,
        created_at=row.created_at,
        analyzed_count=row.analyzed_count,
        recommendation_count=row.recommendation_count,
        final_n=int(final_n) if final_n is not None else 0,
        max_change_pct=float(max_change_pct) if max_change_pct is not None else None,
        picks=picks,
    )


async def list_screener_records(
    user_id: object,
    strategy: str = "main_force",
    limit: int = 10,
) -> list[MainForceRecordSummary]:
    async with SessionLocal() as session:
        stmt = (
            select(ScreenerRecord)
            .where(
                ScreenerRecord.user_id == user_id,
                ScreenerRecord.strategy == strategy,
            )
            .order_by(ScreenerRecord.created_at.desc())
            .limit(limit)
        )
        rows = (await session.scalars(stmt)).all()
    return [_summary(row) for row in rows]


async def get_screener_record(
    user_id: object,
    record_id: uuid.UUID,
    strategy: str | None = None,
) -> MainForceRecordDetail | None:
    async with SessionLocal() as session:
        row = await session.get(ScreenerRecord, record_id)
        if row is None or row.user_id != user_id:
            return None
        if strategy is not None and row.strategy != strategy:
            return None
        try:
            result = MainForceAnalysisResponse.model_validate(row.result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("选股记录解析失败 %s: %s", record_id, exc)
            return None
        return MainForceRecordDetail(
            id=row.id,
            strategy=row.strategy,
            created_at=row.created_at,
            filters=row.filters or {},
            result=result,
        )

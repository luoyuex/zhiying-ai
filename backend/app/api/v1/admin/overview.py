from typing import Literal

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.db.redis import get_redis
from app.schemas.admin import AdminOverview
from app.services.admin.overview import build_overview

router = APIRouter()


@router.get("/overview", response_model=AdminOverview, summary="后台运营总览")
async def get_overview(
    time_range: Literal["today", "7d"] = Query("today", alias="range"),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AdminOverview:
    return await build_overview(db, redis, time_range)

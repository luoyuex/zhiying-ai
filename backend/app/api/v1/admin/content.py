"""后台内容库接口：跨用户只读查看。"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.common import PageParams
from app.core.deps import get_db
from app.schemas.admin import (
    AdminContentPortfolioDetail,
    AdminContentPortfolioItem,
    AdminContentReportDetail,
    AdminContentReportItem,
    AdminContentScreenerDetail,
    AdminContentScreenerItem,
    AdminContentWatchlistItem,
    Page,
)
from app.services.admin import content as content_service

router = APIRouter()


@router.get(
    "/reports",
    response_model=Page[AdminContentReportItem],
    summary="跨用户报告库",
)
async def list_reports(
    params: PageParams = Depends(),
    q: str | None = Query(None, max_length=100),
    symbol: str | None = Query(None, max_length=12),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminContentReportItem]:
    return await content_service.list_reports(
        db,
        page=params.page,
        page_size=params.page_size,
        q=q,
        symbol=symbol,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/reports/{report_id}",
    response_model=AdminContentReportDetail,
    summary="报告详情（只读）",
)
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AdminContentReportDetail:
    return await content_service.get_report(db, report_id)


@router.get(
    "/screener-records",
    response_model=Page[AdminContentScreenerItem],
    summary="跨用户选股记录",
)
async def list_screener_records(
    params: PageParams = Depends(),
    q: str | None = Query(None, max_length=100),
    strategy: str | None = Query(None, max_length=32),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminContentScreenerItem]:
    return await content_service.list_screener_records(
        db,
        page=params.page,
        page_size=params.page_size,
        q=q,
        strategy=strategy,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/screener-records/{record_id}",
    response_model=AdminContentScreenerDetail,
    summary="选股记录详情（只读）",
)
async def get_screener_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AdminContentScreenerDetail:
    return await content_service.get_screener_record(db, record_id)


@router.get(
    "/portfolio-diagnoses",
    response_model=Page[AdminContentPortfolioItem],
    summary="跨用户组合诊断",
)
async def list_portfolio_diagnoses(
    params: PageParams = Depends(),
    q: str | None = Query(None, max_length=100),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminContentPortfolioItem]:
    return await content_service.list_portfolio_diagnoses(
        db,
        page=params.page,
        page_size=params.page_size,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/portfolio-diagnoses/{record_id}",
    response_model=AdminContentPortfolioDetail,
    summary="组合诊断详情（只读）",
)
async def get_portfolio_diagnosis(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AdminContentPortfolioDetail:
    return await content_service.get_portfolio_diagnosis(db, record_id)


@router.get(
    "/watchlist-items",
    response_model=Page[AdminContentWatchlistItem],
    summary="跨用户自选股",
)
async def list_watchlist(
    params: PageParams = Depends(),
    q: str | None = Query(None, max_length=100),
    symbol: str | None = Query(None, max_length=12),
    db: AsyncSession = Depends(get_db),
) -> Page[AdminContentWatchlistItem]:
    return await content_service.list_watchlist(
        db,
        page=params.page,
        page_size=params.page_size,
        q=q,
        symbol=symbol,
    )

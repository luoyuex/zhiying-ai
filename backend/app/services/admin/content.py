"""后台内容库：跨用户只读查看报告、选股记录、组合诊断与自选。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.db.models.analysis_report import AnalysisReport
from app.db.models.portfolio_diagnosis import PortfolioDiagnosisRecord
from app.db.models.screener_record import ScreenerRecord
from app.db.models.stock import Stock
from app.db.models.user import User
from app.db.models.watchlist import WatchlistItem
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


def _email_like(q: str | None):
    return func.lower(User.email).like(f"%{q.strip().lower()}%") if q else None


def _report_item(row: AnalysisReport, email: str | None) -> AdminContentReportItem:
    decision = (row.report or {}).get("decision") or {}
    return AdminContentReportItem(
        id=row.id,
        user_id=row.user_id,
        user_email=email,
        symbol=row.symbol,
        name=row.name,
        rating=row.rating,
        confidence=row.confidence,
        rating_change=row.rating_change,
        prev_rating=row.prev_rating,
        decision_source=str(decision.get("decision_source") or ""),
        created_at=row.created_at,
    )


async def list_reports(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    symbol: str | None = None,
    date_from=None,
    date_to=None,
) -> Page[AdminContentReportItem]:
    stmt = select(AnalysisReport, User.email).outerjoin(
        User, User.id == AnalysisReport.user_id
    )
    count_stmt = select(func.count()).select_from(AnalysisReport).outerjoin(
        User, User.id == AnalysisReport.user_id
    )
    conditions = []
    if symbol:
        conditions.append(AnalysisReport.symbol == symbol.strip())
    if q:
        keyword = q.strip()
        conditions.append(
            _email_like(keyword)
            | AnalysisReport.name.ilike(f"%{keyword}%")
            | AnalysisReport.symbol.like(f"%{keyword}%")
        )
    if date_from:
        conditions.append(AnalysisReport.created_at >= date_from)
    if date_to:
        conditions.append(AnalysisReport.created_at <= date_to)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.execute(
            stmt.order_by(AnalysisReport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[_report_item(row.AnalysisReport, row.email) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_report(db: AsyncSession, report_id) -> AdminContentReportDetail:
    row = (
        await db.execute(
            select(AnalysisReport, User.email)
            .outerjoin(User, User.id == AnalysisReport.user_id)
            .where(AnalysisReport.id == report_id)
        )
    ).first()
    if row is None:
        raise errors.not_found("报告不存在")
    item = _report_item(row.AnalysisReport, row.email)
    return AdminContentReportDetail(**item.model_dump(), report=row.AnalysisReport.report or {})


def _screener_item(row: ScreenerRecord, email: str | None) -> AdminContentScreenerItem:
    raw = row.result or {}
    picks = [
        {
            "rank": rec.get("rank", index),
            "symbol": rec.get("symbol", ""),
            "name": rec.get("name", ""),
        }
        for index, rec in enumerate(raw.get("recommendations") or [], start=1)
        if isinstance(rec, dict)
    ]
    return AdminContentScreenerItem(
        id=row.id,
        user_id=row.user_id,
        user_email=email,
        strategy=row.strategy,
        analyzed_count=row.analyzed_count,
        recommendation_count=row.recommendation_count,
        model=row.model,
        picks=picks,
        created_at=row.created_at,
    )


async def list_screener_records(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    strategy: str | None = None,
    date_from=None,
    date_to=None,
) -> Page[AdminContentScreenerItem]:
    stmt = select(ScreenerRecord, User.email).outerjoin(
        User, User.id == ScreenerRecord.user_id
    )
    count_stmt = select(func.count()).select_from(ScreenerRecord).outerjoin(
        User, User.id == ScreenerRecord.user_id
    )
    conditions = []
    if strategy:
        conditions.append(ScreenerRecord.strategy == strategy)
    if q:
        conditions.append(_email_like(q))
    if date_from:
        conditions.append(ScreenerRecord.created_at >= date_from)
    if date_to:
        conditions.append(ScreenerRecord.created_at <= date_to)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.execute(
            stmt.order_by(ScreenerRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[_screener_item(row.ScreenerRecord, row.email) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_screener_record(db: AsyncSession, record_id) -> AdminContentScreenerDetail:
    row = (
        await db.execute(
            select(ScreenerRecord, User.email)
            .outerjoin(User, User.id == ScreenerRecord.user_id)
            .where(ScreenerRecord.id == record_id)
        )
    ).first()
    if row is None:
        raise errors.not_found("选股记录不存在")
    item = _screener_item(row.ScreenerRecord, row.email)
    return AdminContentScreenerDetail(
        **item.model_dump(),
        filters=row.ScreenerRecord.filters or {},
        result=row.ScreenerRecord.result or {},
    )


def _portfolio_item(
    row: PortfolioDiagnosisRecord, email: str | None
) -> AdminContentPortfolioItem:
    return AdminContentPortfolioItem(
        id=row.id,
        user_id=row.user_id,
        user_email=email,
        health_score=row.health_score,
        position_count=row.position_count,
        summary=row.summary,
        created_at=row.created_at,
    )


async def list_portfolio_diagnoses(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    date_from=None,
    date_to=None,
) -> Page[AdminContentPortfolioItem]:
    stmt = select(PortfolioDiagnosisRecord, User.email).outerjoin(
        User, User.id == PortfolioDiagnosisRecord.user_id
    )
    count_stmt = (
        select(func.count())
        .select_from(PortfolioDiagnosisRecord)
        .outerjoin(User, User.id == PortfolioDiagnosisRecord.user_id)
    )
    conditions = []
    if q:
        conditions.append(_email_like(q))
    if date_from:
        conditions.append(PortfolioDiagnosisRecord.created_at >= date_from)
    if date_to:
        conditions.append(PortfolioDiagnosisRecord.created_at <= date_to)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.execute(
            stmt.order_by(PortfolioDiagnosisRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[_portfolio_item(row.PortfolioDiagnosisRecord, row.email) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_portfolio_diagnosis(
    db: AsyncSession, record_id
) -> AdminContentPortfolioDetail:
    row = (
        await db.execute(
            select(PortfolioDiagnosisRecord, User.email)
            .outerjoin(User, User.id == PortfolioDiagnosisRecord.user_id)
            .where(PortfolioDiagnosisRecord.id == record_id)
        )
    ).first()
    if row is None:
        raise errors.not_found("组合诊断不存在")
    item = _portfolio_item(row.PortfolioDiagnosisRecord, row.email)
    return AdminContentPortfolioDetail(
        **item.model_dump(),
        model=row.PortfolioDiagnosisRecord.model,
        report=row.PortfolioDiagnosisRecord.report or {},
    )


async def list_watchlist(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    symbol: str | None = None,
) -> Page[AdminContentWatchlistItem]:
    stmt = (
        select(WatchlistItem, User.email, Stock.name)
        .outerjoin(User, User.id == WatchlistItem.user_id)
        .outerjoin(Stock, Stock.code == WatchlistItem.symbol)
    )
    count_stmt = (
        select(func.count())
        .select_from(WatchlistItem)
        .outerjoin(User, User.id == WatchlistItem.user_id)
    )
    conditions = []
    if symbol:
        conditions.append(WatchlistItem.symbol == symbol.strip())
    if q:
        conditions.append(_email_like(q))
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.execute(
            stmt.order_by(WatchlistItem.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        AdminContentWatchlistItem(
            id=row.WatchlistItem.id,
            user_id=row.WatchlistItem.user_id,
            user_email=row.email,
            symbol=row.WatchlistItem.symbol,
            name=row.name or row.WatchlistItem.symbol,
            note=row.WatchlistItem.note,
            cost_price=(
                float(row.WatchlistItem.cost_price)
                if row.WatchlistItem.cost_price is not None
                else None
            ),
            quantity=row.WatchlistItem.quantity,
            created_at=row.WatchlistItem.created_at,
        )
        for row in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)

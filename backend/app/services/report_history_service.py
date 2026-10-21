"""分析报告历史：落库、列表与详情。"""

import uuid

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.analysis_report import AnalysisReport
from app.db.session import SessionLocal
from app.schemas.ai import AIAnalysisResponse
from app.schemas.report import AnalysisReportDetail, AnalysisReportSummary

logger = get_logger(__name__)


async def save_analysis_report(
    user_id: object,
    report: AIAnalysisResponse,
) -> uuid.UUID:
    decision = report.decision
    rating = decision.rating if decision else report.analysis.rating
    confidence = decision.confidence if decision else report.analysis.confidence
    async with SessionLocal() as session:
        row = AnalysisReport(
            user_id=user_id,
            symbol=report.symbol,
            name=report.name,
            rating=rating,
            confidence=confidence,
            model=report.model,
            prompt_version=report.prompt_version,
            report=report.model_dump(mode="json"),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def list_analysis_reports(
    user_id: object,
    *,
    symbol: str | None = None,
    limit: int = 10,
) -> list[AnalysisReportSummary]:
    async with SessionLocal() as session:
        stmt = (
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user_id)
            .order_by(AnalysisReport.created_at.desc())
            .limit(limit)
        )
        if symbol:
            stmt = stmt.where(AnalysisReport.symbol == symbol)
        rows = (await session.scalars(stmt)).all()

    summaries: list[AnalysisReportSummary] = []
    for row in rows:
        decision = (row.report or {}).get("decision") or {}
        summaries.append(
            AnalysisReportSummary(
                id=row.id,
                symbol=row.symbol,
                name=row.name,
                rating=row.rating,
                confidence=row.confidence,
                model=row.model,
                prompt_version=row.prompt_version,
                decision_source=str(decision.get("decision_source") or ""),
                created_at=row.created_at,
            )
        )
    return summaries


async def get_analysis_report(
    user_id: object,
    report_id: uuid.UUID,
) -> AnalysisReportDetail | None:
    async with SessionLocal() as session:
        row = await session.get(AnalysisReport, report_id)
        if row is None or row.user_id != user_id:
            return None
        try:
            report = AIAnalysisResponse.model_validate(row.report)
        except Exception as exc:  # noqa: BLE001
            logger.warning("历史报告解析失败 %s: %s", report_id, exc)
            return None
        return AnalysisReportDetail(
            id=row.id,
            created_at=row.created_at,
            report=report,
        )

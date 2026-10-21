"""分析报告历史接口。"""

import uuid

from fastapi import APIRouter, Depends, Query

from app.core import errors
from app.core.deps import get_current_user
from app.db.models.user import User
from app.schemas.report import AnalysisReportDetail, AnalysisReportSummary
from app.services.report_history_service import (
    get_analysis_report,
    list_analysis_reports,
)

router = APIRouter(prefix="/analysis/reports", tags=["历史报告"])


@router.get("", response_model=list[AnalysisReportSummary], summary="历史分析列表")
async def list_reports(
    symbol: str | None = Query(None, min_length=6, max_length=6),
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
) -> list[AnalysisReportSummary]:
    return await list_analysis_reports(user.id, symbol=symbol, limit=limit)


@router.get("/{report_id}", response_model=AnalysisReportDetail, summary="历史报告详情")
async def get_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> AnalysisReportDetail:
    detail = await get_analysis_report(user.id, report_id)
    if detail is None:
        raise errors.not_found("分析报告不存在")
    return detail

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.ai import AIAnalysisResponse


class AnalysisReportSummary(BaseModel):
    id: uuid.UUID
    symbol: str
    name: str
    rating: str
    confidence: int
    model: str
    prompt_version: str
    decision_source: str = ""
    created_at: datetime


class AnalysisReportDetail(BaseModel):
    id: uuid.UUID
    created_at: datetime
    report: AIAnalysisResponse

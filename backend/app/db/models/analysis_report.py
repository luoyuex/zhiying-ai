import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"
    __table_args__ = (
        Index(
            "ix_analysis_reports_user_symbol_created",
            "user_id",
            "symbol",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(6), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    rating: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    report: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rating_change: Mapped[str | None] = mapped_column(String(8))
    prev_rating: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AnalysisReport {self.symbol} {self.created_at}>"

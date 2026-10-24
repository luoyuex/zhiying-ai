"""定时任务执行记录：每个用户、每条任务线、每天一行，记录是否入队与跳过原因。"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (
        UniqueConstraint(
            "run_date", "user_id", "line", name="uq_automation_runs_day_user_line"
        ),
        Index("ix_automation_runs_user_date", "user_id", "run_date"),
        Index("ix_automation_runs_date_status", "run_date", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # screener / analysis
    line: Mapped[str] = mapped_column(String(16), nullable=False)
    # enqueued / no_tasks / skipped_quota / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    enqueued: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AutomationRun {self.run_date} {self.user_id} {self.line} {self.status}>"

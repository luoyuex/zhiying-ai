"""AI 任务台账：Redis 只保存实时状态，这里保存可检索的历史。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        Index("ix_ai_jobs_created_at", "created_at"),
        Index("ix_ai_jobs_user_created", "user_id", "created_at"),
        Index("ix_ai_jobs_kind_status_created", "kind", "status", "created_at"),
    )

    # 与 Redis 中的 job_id 一致（uuid4().hex）
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str | None] = mapped_column(String(12))
    strategy: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str] = mapped_column(String(64), default="", server_default="", nullable=False)
    trigger: Mapped[str] = mapped_column(
        String(16), default="manual", server_default="manual", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    token_total: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    error_code: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSONB)

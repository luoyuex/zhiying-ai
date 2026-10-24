"""LLM 调用流水：每次模型调用一行，用于成本与质量统计。"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_created_at", "created_at"),
        Index("ix_llm_calls_user_created", "user_id", "created_at"),
        Index("ix_llm_calls_task_created", "task", "created_at"),
        Index("ix_llm_calls_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id: Mapped[str | None] = mapped_column(String(32))
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(32))
    finish_reason: Mapped[str | None] = mapped_column(String(24))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

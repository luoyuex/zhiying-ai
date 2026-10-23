"""用户定时任务设置：每日自动选股与自动分析自选股的开关与参数。"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutomationSettings(Base):
    __tablename__ = "user_automation_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    screener_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    analysis_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    # 每条任务线各自的执行时间（Asia/Shanghai，24 小时制）
    screener_run_hour: Mapped[int] = mapped_column(
        default=17, server_default=text("17"), nullable=False
    )
    screener_run_minute: Mapped[int] = mapped_column(
        default=35, server_default=text("35"), nullable=False
    )
    analysis_run_hour: Mapped[int] = mapped_column(
        default=17, server_default=text("17"), nullable=False
    )
    analysis_run_minute: Mapped[int] = mapped_column(
        default=35, server_default=text("35"), nullable=False
    )
    # {"main_force": {"enabled": true, "filters": {...}}, ...}，key 为启用的策略
    strategy_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AutomationSettings user={self.user_id}>"

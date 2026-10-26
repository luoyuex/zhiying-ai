"""关键价位提醒：价格上破 / 下破目标价后触发并邮件通知。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PriceAlert(Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        Index("ix_price_alerts_user_status", "user_id", "status"),
        Index("ix_price_alerts_symbol_status", "symbol", "status"),
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
    symbol: Mapped[str] = mapped_column(String(6), nullable=False)
    name: Mapped[str] = mapped_column(String(64), server_default="", nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # above / below
    target_price: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    # custom / entry / take_profit / stop_loss；报告价位创建的提醒带 report_id
    kind: Mapped[str] = mapped_column(
        String(16), default="custom", server_default="custom", nullable=False
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_reports.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(12), server_default="active", nullable=False
    )  # active / triggered
    triggered_price: Mapped[float | None] = mapped_column(Numeric(12, 3))
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PriceAlert {self.user_id} {self.symbol} {self.direction} {self.target_price}>"

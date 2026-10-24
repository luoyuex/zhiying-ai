"""自选股持仓调整记录：成本价 / 数量每次变更落一条。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PositionChangeLog(Base):
    __tablename__ = "position_change_logs"
    __table_args__ = (
        Index(
            "ix_position_change_logs_user_symbol_created",
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
    symbol: Mapped[str] = mapped_column(String(6), nullable=False)
    old_cost_price: Mapped[float | None] = mapped_column(Numeric(12, 3))
    new_cost_price: Mapped[float | None] = mapped_column(Numeric(12, 3))
    old_quantity: Mapped[int | None] = mapped_column(Integer)
    new_quantity: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PositionChangeLog {self.user_id} {self.symbol} {self.created_at}>"

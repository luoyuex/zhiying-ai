"""A 股基础信息表：代码 / 名称 / 交易所 / 拼音。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Stock(Base):
    __tablename__ = "stocks"

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(2), nullable=False)
    # 全拼（guizhoumaotai）与首字母（gzmt），种子时由 pypinyin 生成
    pinyin: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    abbr: Mapped[str] = mapped_column(String(16), default="", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Stock {self.code} {self.name}>"

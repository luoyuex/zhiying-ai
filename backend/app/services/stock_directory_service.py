"""股票基础库：拼音生成、全量同步与本地搜索。"""

import re

from pypinyin import Style, lazy_pinyin
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.logging import get_logger
from app.db.models.stock import Stock
from app.db.session import SessionLocal
from app.providers.models import StockBasic
from app.schemas.stock import StockSearchItem

logger = get_logger(__name__)

_BATCH_SIZE = 500
_UNSAFE_CHARS = re.compile(r"[%_\\]")


def build_pinyin(name: str) -> tuple[str, str]:
    """中文名 → (全拼, 首字母)，忽略 *ST / N / C 等 ASCII 标记。"""
    hanzi = "".join(ch for ch in name if "\u4e00" <= ch <= "\u9fff")
    if not hanzi:
        return "", ""
    full = "".join(lazy_pinyin(hanzi)).lower()[:64]
    abbr = "".join(lazy_pinyin(hanzi, style=Style.FIRST_LETTER)).lower()[:16]
    return full, abbr


async def sync_stocks(
    items: list[StockBasic], *, deactivate_missing: bool = True
) -> dict[str, int]:
    """全量 upsert；默认把本次未出现的代码标记为停用（退市/更名）。"""
    rows = []
    for item in items:
        pinyin, abbr = build_pinyin(item.name)
        rows.append(
            {
                "code": item.code,
                "name": item.name,
                "exchange": item.exchange,
                "pinyin": pinyin,
                "abbr": abbr,
                "is_active": True,
            }
        )

    deactivated = 0
    async with SessionLocal() as session:
        for start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[start : start + _BATCH_SIZE]
            stmt = insert(Stock).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Stock.code],
                set_={
                    "name": stmt.excluded.name,
                    "exchange": stmt.excluded.exchange,
                    "pinyin": stmt.excluded.pinyin,
                    "abbr": stmt.excluded.abbr,
                    "is_active": True,
                    "updated_at": func.now(),
                },
            )
            await session.execute(stmt)

        if rows and deactivate_missing:
            result = await session.execute(
                update(Stock)
                .where(Stock.code.notin_([row["code"] for row in rows]), Stock.is_active.is_(True))
                .values(is_active=False)
            )
            deactivated = result.rowcount or 0

        await session.commit()

    logger.info("股票库同步完成：%s 条，停用 %s 条", len(rows), deactivated)
    return {"synced": len(rows), "deactivated": deactivated}


async def search_stocks(query: str, limit: int = 10) -> list[StockSearchItem]:
    """支持代码 / 名称 / 全拼 / 首字母；代码、拼音前缀优先。"""
    keyword = _UNSAFE_CHARS.sub("", (query or "").strip().lower())
    if not keyword:
        return []

    contains = f"%{keyword}%"
    rank = case(
        (Stock.code == keyword, 0),
        (Stock.abbr == keyword, 1),
        (Stock.pinyin == keyword, 2),
        (Stock.code.startswith(keyword), 3),
        (Stock.name.startswith(keyword), 4),
        (Stock.abbr.startswith(keyword), 5),
        (Stock.pinyin.startswith(keyword), 6),
        else_=7,
    )

    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(Stock)
                .where(
                    Stock.is_active.is_(True),
                    or_(
                        Stock.code.startswith(keyword),
                        Stock.name.ilike(contains),
                        Stock.abbr.startswith(keyword),
                        Stock.pinyin.startswith(keyword),
                    ),
                )
                .order_by(rank, Stock.code)
                .limit(limit)
            )
        ).all()

    return [
        StockSearchItem(code=row.code, name=row.name, exchange=row.exchange)
        for row in rows
    ]

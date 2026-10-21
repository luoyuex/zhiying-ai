"""读取用户在自选股中记录的持仓信息。"""

from sqlalchemy import select

from app.db.models.watchlist import WatchlistItem
from app.db.session import SessionLocal
from app.schemas.position import UserPosition


async def load_user_position(user_id: object, symbol: str) -> UserPosition | None:
    """自选股记录存在即视为关注该股票；成本/数量可缺省。"""
    async with SessionLocal() as session:
        row = await session.scalar(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.symbol == symbol,
            )
        )
    if row is None:
        return None
    return UserPosition(
        cost_price=float(row.cost_price) if row.cost_price is not None else None,
        quantity=row.quantity,
        note=row.note,
    )

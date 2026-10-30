"""股票搜索与基础信息。"""

from pydantic import BaseModel


class StockSearchItem(BaseModel):
    code: str
    name: str
    exchange: str


class HotStockItem(BaseModel):
    """首页「热门股票」：按当日成交额排序的活跃标的。"""

    code: str
    name: str
    price: float | None = None
    change_pct: float | None = None

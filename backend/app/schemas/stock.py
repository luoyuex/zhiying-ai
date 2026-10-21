"""股票搜索与基础信息。"""

from pydantic import BaseModel


class StockSearchItem(BaseModel):
    code: str
    name: str
    exchange: str

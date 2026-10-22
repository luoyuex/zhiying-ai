from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    id: str
    kind: Literal["announcement", "article"]
    title: str
    summary: str = ""
    url: str
    source: str = ""
    published_at: str = ""


class CompanyNewsData(BaseModel):
    symbol: str
    announcements: list[NewsItem] = Field(default_factory=list)
    articles: list[NewsItem] = Field(default_factory=list)
    source: str = "eastmoney_announcement+eastmoney_news"
    fetched_at: datetime
    """部分数据源失败时为 True，页面对应列表可能为空。"""
    partial: bool = False

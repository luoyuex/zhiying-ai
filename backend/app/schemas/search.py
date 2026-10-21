from datetime import datetime

from pydantic import BaseModel, Field


class WebSource(BaseModel):
    title: str
    url: str
    date: str = ""
    site: str = ""
    summary: str = ""


class WebSearchResult(BaseModel):
    query: str
    success: bool
    pages: list[WebSource] = Field(default_factory=list)
    version: str = ""
    error: str | None = None
    fetched_at: datetime
    cached: bool = False
